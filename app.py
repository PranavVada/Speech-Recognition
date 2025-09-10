import os, io, hashlib
import gradio as gr
import numpy as np
import soundfile as sf
from datetime import datetime
from base64 import b64decode

from sqlalchemy import create_engine, Column, Integer, String, LargeBinary, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is not set. On Render, connect a Postgres and set DATABASE_URL.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class AudioText(Base):
    __tablename__ = "audio_text"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    audio_data = Column(LargeBinary, nullable=False)
    audio_hash = Column(String(64), nullable=False, unique=True)
    transcript = Column(String, nullable=True)
    description = Column(String, nullable=True)
    sample_rate = Column(Integer, nullable=True)
    date = Column(String, default=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), nullable=True)
    meta = relationship("SubmissionMeta", back_populates="audio", uselist=False, cascade="all, delete-orphan")

Index("ix_audio_text_audio_hash", AudioText.audio_hash, unique=True)

class SubmissionMeta(Base):
    __tablename__ = "submission_meta"
    id = Column(Integer, primary_key=True)
    audio_id = Column(Integer, ForeignKey("audio_text.id", ondelete="CASCADE"), nullable=False, unique=True)
    ip_address = Column(String, nullable=True)
    username = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    timestamp = Column(String, default=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), nullable=True)
    audio = relationship("AudioText", back_populates="meta")

Base.metadata.create_all(engine)

MAX_BYTES = 10 * 1024 * 1024

def _client_ip(req: gr.Request):
    if not req:
        return None
    xff = req.headers.get("x-forwarded-for") if hasattr(req, "headers") else None
    if xff:
        return xff.split(",")[0].strip()
    if hasattr(req, "client") and req.client and getattr(req.client, "host", None):
        return req.client.host
    return None

def _username_from_request(req: gr.Request):
    auth = req.headers.get("authorization") if hasattr(req, "headers") else None
    if auth and auth.lower().startswith("basic "):
        try:
            userpass = b64decode(auth.split(" ", 1)[1]).decode("utf-8")
            return userpass.split(":", 1)[0]
        except Exception:
            return None
    return None

def process_audio(audio, title, transcript, description, request: gr.Request):
    if not title or not title.strip():
        return "Title is required."
    if audio is None:
        return "Audio is required."

    sr, audio_np = audio
    if not isinstance(audio_np, np.ndarray) or audio_np.size == 0:
        return "Invalid audio input."

    buf = io.BytesIO()
    sf.write(buf, audio_np, int(sr), format="WAV", subtype="PCM_16")
    wav_bytes = buf.getvalue()
    if len(wav_bytes) > MAX_BYTES:
        return "Audio file is too large. Please upload a file smaller than 10MB."
    audio_hash = hashlib.sha256(wav_bytes).hexdigest()

    ip = _client_ip(request)
    ua = request.headers.get("user-agent") if hasattr(request, "headers") else None
    user = _username_from_request(request)

    session = SessionLocal()
    try:
        existing = session.query(AudioText).filter_by(audio_hash=audio_hash).first()
        if existing:
            return "Duplicate submission detected for this audio."

        entry = AudioText(
            title=title.strip(),
            audio_data=wav_bytes,
            audio_hash=audio_hash,
            transcript=(transcript.strip() or None) if transcript else None,
            description=(description.strip() or None) if description else None,
            sample_rate=int(sr),
            date=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        )
        session.add(entry)
        session.flush()

        meta = SubmissionMeta(
            audio_id=entry.id,
            ip_address=ip,
            username=user,
            user_agent=ua,
            timestamp=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        )
        session.add(meta)
        session.commit()
        return f"Saved. Request from {ip or 'unknown IP'}."
    except Exception as e:
        session.rollback()
        return f"An error occurred while saving data: {str(e)}"
    finally:
        session.close()

title_tb = gr.Textbox(placeholder="Enter a title", lines=1, label="Title (mandatory)")
transcript_tb = gr.Textbox(placeholder="(Optional) Transcript", lines=2, label="Transcript")
description_tb = gr.Textbox(placeholder="(Optional) Describe the context", lines=2, label="Description")

demo = gr.Interface(
    fn=process_audio,
    inputs=[
        gr.Audio(sources=["microphone", "upload"], type="numpy", label="Audio (mandatory)"),
        title_tb,
        transcript_tb,
        description_tb,
    ],
    outputs="text",
    live=False
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))

    auth_pairs = []
    auth_env = os.getenv("BASIC_AUTH_USERS", "").strip()
    if auth_env:
        for pair in auth_env.replace(";", ",").split(","):
            pair = pair.strip()
            if pair and ":" in pair:
                u, p = pair.split(":", 1)
                auth_pairs.append((u.strip(), p.strip()))
    auth_arg = auth_pairs if auth_pairs else None

    demo.queue()
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        auth=auth_arg,
        auth_message="Login to access the uploader"
    )

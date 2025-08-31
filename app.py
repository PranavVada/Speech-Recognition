import os, io
import gradio as gr
import numpy as np
import soundfile as sf
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, LargeBinary
from sqlalchemy.orm import sessionmaker, declarative_base

# -------- Database setup (Render Postgres) --------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is not set. On Render, connect a Postgres and set DATABASE_URL.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class AudioText(Base):
    __tablename__ = "audio_text"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=True)
    audio_data = Column(LargeBinary, nullable=True)   # BYTEA in Postgres
    transcript = Column(String, nullable=True)        # maps to TEXT in Postgres
    description = Column(String, nullable=True)
    sample_rate = Column(Integer, nullable=True)
    date = Column(String, default=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), nullable=True)

Base.metadata.create_all(engine)

# -------- App logic --------
MAX_BYTES = 10 * 1024 * 1024  # 10 MB

def process_audio(audio, title, transcript, description):
    wav_bytes = None
    sr_val = None

    if audio is not None:
        sr, audio_np = audio  # (sample_rate, np.ndarray)
        # Quick size guard on raw ndarray
        if audio_np.nbytes > MAX_BYTES:
            return "Audio file is too large. Please upload a file smaller than 10MB."
        # Convert to WAV bytes
        buf = io.BytesIO()
        sf.write(buf, audio_np, int(sr), format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()
        sr_val = int(sr)

    session = SessionLocal()
    try:
        entry = AudioText(
            title=(title.strip() or None) if title else None,
            audio_data=wav_bytes,
            transcript=(transcript.strip() or None) if transcript else None,
            description=(description.strip() or None) if description else None,
            sample_rate=sr_val,
            date=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        )
        session.add(entry)
        session.commit()
        return "Data saved successfully to PostgreSQL on Render."
    except Exception as e:
        session.rollback()
        return f"An error occurred while saving data: {str(e)}"
    finally:
        session.close()

demo = gr.Interface(
    fn=process_audio,
    inputs=[
        gr.Audio(sources=["microphone", "upload"], type="numpy"),
        gr.Textbox(placeholder="(Optional) Title", lines=1, label="Title"),
        gr.Textbox(placeholder="(Optional) Transcript", lines=2, label="Transcript"),
        gr.Textbox(placeholder="(Optional) Describe the context", lines=2, label="Description"),
    ],
    outputs="text",
    live=False
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    demo.queue()
    # Bind to 0.0.0.0 and the PORT Render provides
    demo.launch(server_name="0.0.0.0", server_port=port, share=False)

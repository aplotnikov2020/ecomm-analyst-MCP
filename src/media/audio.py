"""Audio transcription using Google Cloud Speech-to-Text."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> Optional[str]:
    """Transcribe audio bytes to text using Google Cloud Speech-to-Text.

    Supports WhatsApp audio formats: ogg/opus, mp4, wav.
    Returns None if transcription fails (caller should ask user to type instead).
    """
    try:
        from google.cloud import speech  # type: ignore[import]

        client = speech.SpeechClient()

        # Map mime types to Google Speech encoding
        encoding_map = {
            "audio/ogg": speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
            "audio/ogg; codecs=opus": speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
            "audio/mp4": speech.RecognitionConfig.AudioEncoding.MP3,
            "audio/wav": speech.RecognitionConfig.AudioEncoding.LINEAR16,
            "audio/mpeg": speech.RecognitionConfig.AudioEncoding.MP3,
        }

        encoding = encoding_map.get(mime_type.lower(), speech.RecognitionConfig.AudioEncoding.OGG_OPUS)

        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            encoding=encoding,
            sample_rate_hertz=16000,
            language_code="en-US",
            alternative_language_codes=["es-ES", "fr-FR", "de-DE", "zh-CN", "ar-SA"],
            enable_automatic_punctuation=True,
            model="latest_long",
        )

        response = client.recognize(config=config, audio=audio)

        if not response.results:
            logger.warning("Speech-to-Text returned no results")
            return None

        transcript = " ".join(
            result.alternatives[0].transcript
            for result in response.results
            if result.alternatives
        )
        confidence = response.results[0].alternatives[0].confidence if response.results[0].alternatives else 0
        logger.info(f"Transcribed audio: {len(transcript)} chars, confidence={confidence:.2f}")
        return transcript.strip() or None

    except ImportError:
        logger.warning("google-cloud-speech not installed — audio transcription unavailable")
        return None
    except Exception as exc:
        logger.error(f"Audio transcription failed: {exc}")
        return None

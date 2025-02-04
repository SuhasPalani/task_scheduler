import os
import csv
import time
import logging
import tempfile
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Tuple

import schedule
import sounddevice as sd
import numpy as np
import soundfile as sf
from twilio.rest import Client
from dotenv import load_dotenv
import openai
import dateparser
from pydub import AudioSegment
from pydub.playback import play

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class TaskConfig:
    """Configuration for task management"""
    csv_file: str = 'tasks.csv'
    sample_rate: int = 16000
    channels: int = 1
    record_duration: int = 3
    max_retries: int = 3
    temp_dir: str = os.path.join(os.path.expanduser('~'), 'voice_scheduler_temp')

@dataclass
class Task:
    """Represents a scheduled task"""
    name: str
    due_date: str
    deadline_time: str

class AudioManager:
    """Handles audio recording and playback operations"""
    def __init__(self, config: TaskConfig):
        self.config = config
        self._ensure_temp_dir()
    
    def _ensure_temp_dir(self):
        """Ensure temporary directory exists with proper permissions"""
        os.makedirs(self.config.temp_dir, exist_ok=True)
        
    def _get_temp_path(self, suffix: str) -> str:
        """Generate a temporary file path"""
        return os.path.join(
            self.config.temp_dir,
            f"temp_{int(time.time())}_{os.getpid()}{suffix}"
        )
        
    def text_to_speech(self, text: str) -> None:
        """Convert text to speech using OpenAI TTS"""
        temp_mp3 = self._get_temp_path(".mp3")
        temp_wav = self._get_temp_path(".wav")
        
        try:
            # Get the speech response from OpenAI
            response = openai.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text
            )
            
            # Save the response content to MP3 file
            with open(temp_mp3, 'wb') as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
            
            # Convert to WAV and play
            audio = AudioSegment.from_mp3(temp_mp3)
            audio.export(temp_wav, format='wav')
            
            # Play using sounddevice
            wav_data, samplerate = sf.read(temp_wav)
            sd.play(wav_data, samplerate)
            sd.wait()
            
        except Exception as e:
            logger.error(f"Error in text_to_speech: {e}")
            raise
        finally:
            # Clean up temporary files
            for temp_file in [temp_mp3, temp_wav]:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as e:
                    logger.warning(f"Failed to remove temporary file {temp_file}: {e}")
    
    def record_audio(self) -> np.ndarray:
        """Record audio from microphone"""
        try:
            logger.info(f"Recording for {self.config.record_duration} seconds...")
            audio = sd.rec(
                int(self.config.record_duration * self.config.sample_rate),
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype='int16'
            )
            sd.wait()
            return audio
        except Exception as e:
            logger.error(f"Error recording audio: {e}")
            raise
    
    def save_audio(self, audio: np.ndarray) -> str:
        """Save audio to temporary file"""
        temp_path = self._get_temp_path(".wav")
        try:
            sf.write(temp_path, audio, self.config.sample_rate)
            return temp_path
        except Exception as e:
            logger.error(f"Error saving audio: {e}")
            raise

class TaskManager:
    """Manages task operations including creation and storage"""
    def __init__(self, config: TaskConfig, audio_manager: AudioManager):
        self.config = config
        self.audio_manager = audio_manager
        self._initialize_csv()
        
        # Load environment variables
        load_dotenv()
        
        # Initialize APIs
        openai.api_key = os.getenv("OPENAI_API_KEY")
        self.twilio_client = Client(
            os.getenv("TWILIO_ACCOUNT_SID"),
            os.getenv("TWILIO_AUTH_TOKEN")
        )
        self.twilio_whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER")
        self.user_whatsapp_number = os.getenv("USER_WHATSAPP_NUMBER")
    
    def _initialize_csv(self) -> None:
        """Initialize CSV file if it doesn't exist"""
        if not os.path.exists(self.config.csv_file):
            with open(self.config.csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Task Name', 'Due Date', 'Deadline Time'])
    
    def speech_to_text(self, audio_path: str) -> str:
        """Convert speech to text using OpenAI Whisper"""
        try:
            with open(audio_path, "rb") as audio_file:
                transcript = openai.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            return transcript.text.strip()
        except Exception as e:
            logger.error(f"Error in speech_to_text: {e}")
            raise
    
    def get_voice_input(self, prompt: Optional[str] = None) -> str:
        """Get user input through voice"""
        if prompt:
            self.audio_manager.text_to_speech(prompt)
        
        for attempt in range(self.config.max_retries):
            audio_path = None
            try:
                audio = self.audio_manager.record_audio()
                audio_path = self.audio_manager.save_audio(audio)
                text = self.speech_to_text(audio_path)
                
                if text:
                    return text
                
                self.audio_manager.text_to_speech("Sorry, I didn't catch that. Please try again.")
            except Exception as e:
                logger.error(f"Error in voice input attempt {attempt + 1}: {e}")
            finally:
                # Clean up temporary audio file
                if audio_path and os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                    except Exception as e:
                        logger.warning(f"Failed to remove temporary file {audio_path}: {e}")
                
        raise ValueError("Maximum retries reached")

    def create_task(self) -> Optional[Task]:
        """Voice-guided task creation flow"""
        try:
            task_name = self.get_voice_input("Please say the task name:")
            date_str = self.get_voice_input("When is this due? For example, you can say 'tomorrow at 3pm'")
            due_date, deadline_time = self.parse_datetime(date_str)
            return Task(task_name, due_date, deadline_time)
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            self.audio_manager.text_to_speech(f"Error creating task: {str(e)}")
            return None

    def parse_datetime(self, text: str) -> Tuple[str, str]:
        """Parse natural language datetime"""
        dt = dateparser.parse(text)
        if not dt:
            raise ValueError("Could not parse datetime")
        
        # Set default time if none provided
        if dt.time() == dt.min.time():
            dt = dt.replace(hour=12, minute=0)
        
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")

    def save_task(self, task: Task) -> None:
        """Save task to CSV file"""
        try:
            with open(self.config.csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([task.name, task.due_date, task.deadline_time])
        except Exception as e:
            logger.error(f"Error saving task: {e}")
            raise

    def send_whatsapp_message(self, message: str) -> None:
        """Send WhatsApp message using Twilio"""
        try:
            self.twilio_client.messages.create(
                body=message,
                from_=f"whatsapp:{self.twilio_whatsapp_number}",
                to=f"whatsapp:{self.user_whatsapp_number}"
            )
            logger.info("WhatsApp message sent successfully")
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            raise

    def schedule_reminder(self, task: Task) -> None:
        """Schedule a reminder for a task"""
        def send_reminder():
            message = f"Reminder: Task '{task.name}' is due on {task.due_date} at {task.deadline_time}"
            self.send_whatsapp_message(message)
        
        schedule.every().day.at(task.deadline_time).do(send_reminder)
        logger.info(f"Reminder scheduled for task '{task.name}' at {task.deadline_time}")

    def send_confirmation(self, task: Task) -> None:
        """Send immediate confirmation for task creation"""
        message = f"Task Created: '{task.name}' has been scheduled. It is due on {task.due_date} at {task.deadline_time}"
        self.send_whatsapp_message(message)

def main():
    """Main application entry point"""
    try:
        config = TaskConfig()
        audio_manager = AudioManager(config)
        task_manager = TaskManager(config, audio_manager)
        
        task_manager.audio_manager.text_to_speech(
            "Welcome to your voice-activated task scheduler. Say 'schedule a task' to begin, or 'exit' to quit."
        )
        
        while True:
            try:
                command = task_manager.get_voice_input("What would you like to do?")
                
                if "schedule" in command.lower() or "task" in command.lower():
                    task = task_manager.create_task()
                    if task:
                        task_manager.save_task(task)
                        task_manager.schedule_reminder(task)
                        task_manager.send_confirmation(task)
                        task_manager.audio_manager.text_to_speech(
                            f"Task '{task.name}' scheduled successfully!"
                        )
                elif "exit" in command.lower():
                    task_manager.audio_manager.text_to_speech(
                        "Exiting the task scheduler. Goodbye!"
                    )
                    break
                else:
                    task_manager.audio_manager.text_to_speech(
                        "I didn't understand that command. Please try again."
                    )
            
            except KeyboardInterrupt:
                task_manager.audio_manager.text_to_speech(
                    "Interrupted by user. Exiting the task scheduler."
                )
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                task_manager.audio_manager.text_to_speech(
                    f"An error occurred: {str(e)}. Please try again."
                )
        
        logger.info("Scheduler running in background. Press Ctrl+C to quit.")
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped.")
    
    finally:
        # Clean up temporary directory
        try:
            if os.path.exists(config.temp_dir):
                for file in os.listdir(config.temp_dir):
                    try:
                        os.remove(os.path.join(config.temp_dir, file))
                    except Exception as e:
                        logger.warning(f"Failed to remove temporary file {file}: {e}")
                os.rmdir(config.temp_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up temporary directory: {e}")

if __name__ == "__main__":
    main()
## Introduction

This project is a **Voice-Activated Task Scheduler**, which allows users to create, manage, and schedule tasks using voice input. The system uses OpenAI's Whisper model for speech-to-text conversion, and Twilio for WhatsApp notifications. The tasks are saved in a CSV file, and reminders are sent at specified times.

### Project Features:
- Voice input for task creation (task name, due date, and time)
- Task confirmation and reminder via WhatsApp
- Text-to-speech feedback using OpenAI
- Audio recording and saving of tasks

## Dependencies

This project requires the following Python libraries:

You can install these dependencies by running the following command:

```bash
pip install -r requirements.txt
```

## Overview of the Code

The project is structured into the following classes and functionalities:

- **TaskConfig**: Manages configuration options like sample rate, record duration, and file paths.
- **Task**: Represents a task with a name, due date, and deadline time.
- **AudioManager**: Handles audio operations like recording, saving, and converting text to speech.
- **TaskManager**: Manages task-related operations, including task creation, saving, and sending reminders.

### Main Functions

1. **Voice Input**: Users speak the task name and due date, and the system converts speech to text using OpenAI's Whisper.
2. **Task Creation**: The task is saved in a CSV file and scheduled for reminders.
3. **Reminder**: A reminder message is sent via WhatsApp using Twilio at the scheduled time.

## Running the Application

To run the application, ensure you have your environment variables configured (e.g., Twilio credentials and OpenAI API key). Then, run the Python script:

```bash
python task_scheduler.py
```

You can interact with the system through voice commands like "schedule a task" or "exit".

## Conclusion

This voice-activated task scheduler can be used to create tasks hands-free and receive reminders, making it a helpful tool for busy schedules. Future improvements could include more advanced natural language processing, multi-language support, and additional notification channels.



### Is Anything Missing?

You should be good with the provided dependencies. However, make sure you have these:

**OpenAI Key and Twilio Credentials**: Ensure `.env` file contains API keys for both OpenAI and Twilio.

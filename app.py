from flask import Flask, request, render_template
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Say
from flask_socketio import SocketIO, emit
import os
import datetime
import csv
import pytz
import azure.cognitiveservices.speech as speechsdk
import openai
import threading

app = Flask(__name__)
socketio = SocketIO(app)

# Azure Speech configuration
SPEECH_KEY = "55d11eb5446d48caa11abbd23a6abddf"  # Replace with your actual Speech key
SPEECH_REGION = "eastus"  # Replace with your actual Speech region

# Azure Function environment variables
OPENAI_API_KEY = "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"  # Replace with your actual OpenAI API key

# Initialize OpenAI client
openai.api_key = OPENAI_API_KEY

# Chat variables
chat_history = ""
summary = ""
prompt_file_path = "pool-cleaning-prompt.csv"
prompt = ""

def from_twilio(request):
    global chat_history
    global summary
    global prompt

    # Extract customer question from Twilio request
    customer_question = request.form.get('Body').lower()  # Assuming 'Body' contains the text message
    
    # Process the customer question and generate response
    chatbot_reply, chat_history = chatbot_response(customer_question, chat_history, summary, prompt)
    
    # Speak response
    text_to_speech(chatbot_reply)
    
    # Emit response to clients
    emit('chat_message', {'message': chatbot_reply}, broadcast=True)
    
    # Return Twilio-compatible response
    return chatbot_reply

def text_to_speech(text: str):
    speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)
    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
    result = speech_synthesizer.speak_text_async(text).get()

def generate_summary(chat_history):
    # Logic to generate summary from chat history
    lines = chat_history.split('\n')
    summary = "Conversation Summary:\n"
    for line in lines:
        if line.startswith("Customer:") or line.startswith("Chatbot:"):
            summary += line + "\n"
    return summary

def read_prompt_from_csv(file_path):
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        prompt_parts = []
        for row in reader:
            question = row['Questions']
            answer = row['Answers']
            prompt_parts.append(f"{question}: {answer}")
        return "\n".join(prompt_parts)

def chatbot_response(message, chat_history, summary, prompt):
    # Corrected to use the full_prompt which includes the latest message.
    current_time = get_current_time()
    full_prompt = f"""
    Current Time: {current_time}
    {prompt}
    {chat_history}
    Customer: {message}
    Agent:"""

    chat_history += f"\nCustomer: {message}"

    # Call OpenAI GPT-3 API to generate response using the full_prompt
    response = openai.Completion.create(
        model="gpt-3.5-turbo-instruct",
        prompt=full_prompt,  # Corrected to use full_prompt instead of prompt
        temperature=0.5,
        max_tokens=150,
        stop=["\n", " Agent:", " Customer:"]
    )

    if response.choices:
        chatbot_reply = response.choices[0].text.strip()
    else:
        chatbot_reply = "No response generated."

    chat_history += f"\nChatbot: {chatbot_reply}"

    return chatbot_reply, chat_history

def get_current_time():
    timezone = pytz.timezone("America/Los_Angeles")
    now = datetime.datetime.now(timezone)
    return now.strftime("%Y-%m-%d %H:%M:%S")

# Endpoint to start the chat
@app.route('/')
def index():
    return render_template('index.html')

# WebSocket event handler
@socketio.on('connect')
def handle_connect():
    emit('chat_message', {'message': 'Connected to the server.'})

# Twilio SMS endpoint
@app.route('/sms', methods=['POST'])
def sms():
    response_text = from_twilio(request)
    resp = MessagingResponse()
    resp.message(response_text)
    return str(resp)

# Twilio voice endpoint
@app.route("/voice", methods=['POST'])
def voice():
    response_text = from_twilio(request)
    response = VoiceResponse()
    response.say(response_text, voice='Polly.Emma')
    response.record()
    response.hangup()
    return str(response)

if __name__ == '__main__':
    prompt = read_prompt_from_csv(prompt_file_path)
    socketio.run(app, debug=True)

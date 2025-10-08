from flask import Flask, request, jsonify
from flask_cors import CORS

# Initialize the Flask application
app = Flask(__name__)
# Enable Cross-Origin Resource Sharing (CORS)
CORS(app)

# A simple function to get the chatbot's response based on user input.
def get_bot_response(user_input):
    """
    Analyzes the user's input and returns a predefined response.

    Args:
        user_input: A string from the user.

    Returns:
        A string containing the bot's reply.
    """
    # Convert user input to lowercase to make the matching case-insensitive.
    text = user_input.lower().strip()

    if "hello" in text:
        return "Hi there! How can I help you today?"
    elif "how are you" in text:
        return "I'm just a bot, but I'm doing great! Thanks for asking."
    elif "bye" in text:
        return "Goodbye! Have a great day."
    else:
        # A default response if the input doesn't match any rules.
        return "I'm sorry, I don't understand that. Please try asking something else."

# API endpoint for the chatbot
@app.route('/chat', methods=['POST'])
def chat():
    """
    Receives a message from the frontend, gets the bot's response,
    and sends it back.
    """
    data = request.get_json()
    user_message = data.get('message')

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    bot_response = get_bot_response(user_message)
    return jsonify({"reply": bot_response})

# Main part of the program to run the server
if __name__ == "__main__":
    print("Starting the chatbot server...")
    # Runs the Flask server on localhost, port 5000
    app.run(port=5000, debug=True)


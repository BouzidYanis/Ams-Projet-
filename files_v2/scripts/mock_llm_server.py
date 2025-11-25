from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/v1/chat/completions", methods=["POST"])
def fastchat_mock():
    data = request.get_json() or {}
    user_msg = ""
    for m in data.get("messages", []):
        if m.get("role") == "user":
            user_msg = m.get("content", user_msg)
    resp = {
        "id": "mock-1",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": f"Mock FastChat: j'ai reçu -> {user_msg}"
                }
            }
        ]
    }
    return jsonify(resp)

if __name__ == "__main__":
    # pip install flask
    app.run(host="0.0.0.0", port=9000, debug=True)
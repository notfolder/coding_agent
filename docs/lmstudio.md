Chat Completions

Use llm.respond(...) to generate completions for a chat conversation.

Quick Example: Generate a Chat Response
The following snippet shows how to obtain the AI's response to a quick chat prompt.

Python (convenience API)Python (scoped resource API)
import lmstudio as lms
model = lms.llm()
print(model.respond("What is the meaning of life?"))

Streaming a Chat Response
The following snippet shows how to stream the AI's response to a chat prompt, displaying text fragments as they are received (rather than waiting for the entire response to be generated before displaying anything).

Python (convenience API)Python (scoped resource API)
import lmstudio as lms
model = lms.llm()

for fragment in model.respond_stream("What is the meaning of life?"):
    print(fragment.content, end="", flush=True)
print() # Advance to a new line at the end of the response

Obtain a Model
First, you need to get a model handle. This can be done using the top-level llm convenience API, or the model method in the llm namespace when using the scoped resource API. For example, here is how to use Qwen2.5 7B Instruct.

Python (convenience API)Python (scoped resource API)
import lmstudio as lms
model = lms.llm("qwen2.5-7b-instruct")

There are other ways to get a model handle. See Managing Models in Memory for more info.

Manage Chat Context
The input to the model is referred to as the "context". Conceptually, the model receives a multi-turn conversation as input, and it is asked to predict the assistant's response in that conversation.

import lmstudio as lms

# Create a chat with an initial system prompt.
chat = lms.Chat("You are a resident AI philosopher.")

# Build the chat context by adding messages of relevant types.
chat.add_user_message("What is the meaning of life?")
# ... continued in next example

See Working with Chats for more information on managing chat context.

Generate a response
You can ask the LLM to predict the next response in the chat context using the respond() method.

Non-streamingStreaming
# The `chat` object is created in the previous step.
result = model.respond(chat)

print(result)

Customize Inferencing Parameters
You can pass in inferencing parameters via the config keyword parameter on .respond().

StreamingNon-streaming
prediction_stream = model.respond_stream(chat, config={
    "temperature": 0.6,
    "maxTokens": 50,
})

See Configuring the Model for more information on what can be configured.

Print prediction stats
You can also print prediction metadata, such as the model used for generation, number of generated tokens, time to first token, and stop reason.

StreamingNon-streaming
# After iterating through the prediction fragments,
# the overall prediction result may be obtained from the stream
result = prediction_stream.result()

print("Model used:", result.model_info.display_name)
print("Predicted tokens:", result.stats.predicted_tokens_count)
print("Time to first token (seconds):", result.stats.time_to_first_token_sec)
print("Stop reason:", result.stats.stop_reason)

Example: Multi-turn Chat
chatbot.py
import lmstudio as lms

model = lms.llm()
chat = lms.Chat("You are a task focused AI assistant")

while True:
    try:
        user_input = input("You (leave blank to exit): ")
    except EOFError:
        print()
        break
    if not user_input:
        break
    chat.add_user_message(user_input)
    prediction_stream = model.respond_stream(
        chat,
        on_message=chat.append,
    )
    print("Bot: ", end="", flush=True)
    for fragment in prediction_stream:
        print(fragment.content, end="", flush=True)
    print()


import os
import gradio as gr
import uvicorn
from app.main import app as fastapi_app

try:
    import spaces

    @spaces.GPU
    def gpu_health_ping(text: str) -> str:
        return f"VeriAudit AI Ready: {text}"

except ImportError:

    def gpu_health_ping(text: str) -> str:
        return f"VeriAudit AI Ready: {text}"


with gr.Blocks(title="VeriAudit AI") as demo:
    gr.Markdown(
        "# VeriAudit AI\n"
        "Antarmuka utama tersedia di jalur root (`/`) dan dokumentasi API di `/docs`."
    )
    with gr.Row(visible=False):
        ping_input = gr.Textbox(value="OK")
        ping_output = gr.Textbox()
        ping_btn = gr.Button("Ping")
        ping_btn.click(fn=gpu_health_ping, inputs=ping_input, outputs=ping_output)

# Mount Gradio di /gradio agar jalur utama '/' tetap menyajikan Split-Pane UI
app = gr.mount_gradio_app(fastapi_app, demo, path="/gradio")

if __name__ == "__main__":
    port = int(os.environ.get("GRADIO_SERVER_PORT") or os.environ.get("PORT") or 7860)
    uvicorn.run(app, host="0.0.0.0", port=port)

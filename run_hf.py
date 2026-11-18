import gradio as gr
import uvicorn
from app.main import app as fastapi_app

with gr.Blocks(title="VeriAudit AI") as demo:
    gr.Markdown(
        "# VeriAudit AI\n"
        "Gunakan antarmuka utama di jalur root (`/`) atau dokumentasi API di `/docs`."
    )

# Mount Gradio di /gradio agar jalur utama '/' tetap menampilkan Split-Pane UI kita
app = gr.mount_gradio_app(fastapi_app, demo, path="/gradio")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)

# novel_proofreader.py
# pip install -r requirements.txt
import gradio as gr
import google.generativeai as genai
import openai
import yaml
import re
import os
import time
from datetime import datetime

# --- 1. 配置加载 (分离) ---
def load_config(config_file):
    """从指定的 yaml 文件加载配置"""
    print(f"[DEBUG] 正在尝试加载 {config_file}...")
    try:
        with open(config_file, "r", encoding="utf-8") as file:
            config = yaml.safe_load(file)
            print(f"[DEBUG] {config_file} 加载成功。")
            return config
    except FileNotFoundError:
        print(f"[ERROR] 错误：找不到 {config_file} 文件。")
        raise FileNotFoundError(f"错误：找不到 {config_file} 文件。")
    except Exception as e:
        print(f"[ERROR] 读取 {config_file} 时出错: {e}")
        raise IOError(f"读取 {config_file} 时出错: {e}")

def load_models():
    """从 models.yaml 加载模型列表"""
    return load_config("models.yaml")

# --- 2. API 调用层 (增加 temperature 参数) ---
def proofread_chapter_with_gemini(chapter_title, chapter_content, model_name, api_key, prompt_template, temperature, proxy_url=None): # <--- 增加 temperature
    """使用 Gemini API 进行校对，包含重试逻辑"""
    if proxy_url:
        os.environ['https_proxy'] = proxy_url
    else:
        if 'https_proxy' in os.environ: del os.environ['https_proxy']

    try:
        # <--- 新增：为 Gemini 配置 Temperature ---
        generation_config = genai.types.GenerationConfig(temperature=temperature)
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name, generation_config=generation_config)
    except Exception as e:
        return f"无法配置或初始化 Gemini 模型: {e}"

    prompt = prompt_template.format(chapter_title=chapter_title, chapter_content=chapter_content)
    max_retries, retry_delay = 2, 3

    try:
        for attempt in range(max_retries + 1):
            try:
                print(f"[DEBUG] [Gemini] 正在为章节 '{chapter_title}' 调用 API (模型: {model_name}, Temp: {temperature}, 尝试: {attempt + 1})...") # <--- 修改日志
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                if attempt >= max_retries: raise e
                print(f"[ERROR] [Gemini] 尝试 {attempt + 1} 失败: {e}. {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
    finally:
        if 'https_proxy' in os.environ: del os.environ['https_proxy']


def proofread_chapter_with_openai(chapter_title, chapter_content, model_name, api_key, prompt_template, temperature, base_url=None): # <--- 增加 temperature
    """使用 OpenAI API 进行校对，包含重试逻辑"""
    try:
        client = openai.OpenAI(api_key=api_key, base_url=base_url if base_url else None)
    except Exception as e:
        return f"无法配置或初始化 OpenAI 客户端: {e}"

    prompt = prompt_template.format(chapter_title=chapter_title, chapter_content=chapter_content)
    max_retries, retry_delay = 2, 3

    for attempt in range(max_retries + 1):
        try:
            print(f"[DEBUG] [OpenAI] 正在为章节 '{chapter_title}' 调用 API (模型: {model_name}, Temp: {temperature}, 尝试: {attempt + 1})...") # <--- 修改日志
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature # <--- 新增：为 OpenAI 配置 Temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            if attempt >= max_retries: raise e
            print(f"[ERROR] [OpenAI] 尝试 {attempt + 1} 失败: {e}. {retry_delay} 秒后重试...")
            time.sleep(retry_delay)

# --- 3. 主处理函数 (增加 temperature 参数) ---
def process_and_proofread_novel(novel_text, api_provider, model_name, prompt_mode, temperature): # <--- 增加 temperature
    """分割文本，根据选择的 API 调度校对任务，并流式返回结果"""
    print(f"\n--- 开始新的校对任务 (API: {api_provider}, Temp: {temperature}) ---") # <--- 修改日志
    if not novel_text.strip():
        yield "请输入小说内容。", gr.File(visible=False)
        return

    try:
        with open(f"prompts/{prompt_mode}.txt", "r", encoding="utf-8") as f: prompt_template = f.read()
        
        if api_provider == "Google Gemini":
            config = load_config("config.yaml")
            api_key, proxy_url = config.get("API_KEY"), config.get("BASE_URL")
            proofread_func = proofread_chapter_with_gemini
            api_args = {'api_key': api_key, 'proxy_url': proxy_url}
        elif api_provider == "OpenAI":
            config = load_config("config_gpt.yaml")
            api_key, base_url = config.get("API_KEY"), config.get("BASE_URL")
            proofread_func = proofread_chapter_with_openai
            api_args = {'api_key': api_key, 'base_url': base_url}
        else:
            yield "错误：无效的 API 提供商。", gr.File(visible=False); return

        if not api_key or "..." in api_key or "YOUR" in api_key:
            yield f"错误: {api_provider} 的 API_KEY 未在配置文件中正确配置。", gr.File(visible=False)
            return
    except Exception as e:
        yield f"加载配置时出错: {e}", gr.File(visible=False); return

    chapters_raw = re.split(r'^(第.*?章)', novel_text, flags=re.MULTILINE)
    chapter_list = []
    if preamble := chapters_raw[0].strip(): chapter_list.append({"title": "【序章/前言】", "content": preamble})
    for i in range(1, len(chapters_raw), 2):
        if content := chapters_raw[i+1].strip(): chapter_list.append({"title": chapters_raw[i].strip(), "content": content})
    if not chapter_list and novel_text.strip(): chapter_list.append({"title": "【全文】", "content": novel_text.strip()})
    if not chapter_list: yield "未能解析出任何文本内容。", gr.File(visible=False); return

    full_report = f"小说校对报告 ({prompt_mode} 模式)\n"
    full_report += f"API: {api_provider} | 模型: {model_name} | Temperature: {temperature}\n" # <--- 修改报告头
    full_report += "====================\n\n"
    yield full_report, gr.File(visible=False)

    for i, chapter in enumerate(chapter_list):
        print(f"[INFO] 开始处理第 {i+1}/{len(chapter_list)} 部分: {chapter['title']}")
        status_prefix = f"校对中 ({i+1}/{len(chapter_list)}): {chapter['title']}\n\n"
        yield full_report + status_prefix, gr.File(visible=False)
        result = ""
        try:
            result = proofread_func(
                chapter_title=chapter['title'], chapter_content=chapter['content'],
                model_name=model_name, prompt_template=prompt_template,
                temperature=temperature, **api_args # <--- 传递 temperature
            )
        except Exception as e:
            result = f"在处理章节 '{chapter['title']}' 时 API 调用最终失败。\n错误: {e}"
        
        full_report += f"{i+1}/{len(chapter_list)}: {chapter['title']}\n\n"
        full_report += result + "\n\n--------------------\n\n"
        yield full_report, gr.File(visible=False)
        time.sleep(1)

    full_report += "小说校对完毕\n\n"
    print("[INFO] 所有章节校对完成。")
    timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    output_filename = f"report_{timestamp}.txt"
    with open(output_filename, "w", encoding="utf-8") as f: f.write(full_report)
    yield full_report, gr.File(value=output_filename, visible=True, label=f"下载报告 ({output_filename})")

# --- 4. Gradio 界面 (动态加载 prompts, 增加 temperature 滑块) ---
try:
    models_data = load_models()
    initial_google_models = models_data.get('google', [])
    initial_openai_models = models_data.get('openai', [])
except Exception as e:
    print(f"[FATAL] 无法加载 models.yaml, 将使用默认值。错误: {e}")
    initial_google_models, initial_openai_models = ["gemini-1.5-flash-latest"], ["gpt-4o"]

# <--- 新增：动态加载 prompt 文件列表 ---
def get_prompt_choices():
    prompt_dir = "prompts"
    if not os.path.isdir(prompt_dir):
        return ["error_no_prompt_dir"]
    try:
        # 返回文件名（不含.txt），并按字母排序
        return sorted([f.replace(".txt", "") for f in os.listdir(prompt_dir) if f.endswith(".txt")])
    except Exception as e:
        print(f"[ERROR] 无法读取 prompts 文件夹: {e}")
        return ["error_reading_prompts"]
prompt_choices = get_prompt_choices()

def update_model_choices(provider):
    if provider == "Google Gemini": choices = initial_google_models
    elif provider == "OpenAI": choices = initial_openai_models
    else: choices = []
    return gr.Radio(choices=choices, value=choices[0] if choices else None)

with gr.Blocks(theme=gr.themes.Soft()) as app:
    gr.Markdown("# 📖 小说文本智能校对器 (多 API 支持)")
    gr.Markdown("将你的小说文本粘贴到下方，选择 API 和模型，工具会自动进行分割和校对。")
    
    with gr.Row():
        with gr.Column(scale=2):
            input_text = gr.Textbox(lines=15, label="小说原文", placeholder="请在这里粘贴你的小说全文...")
            
            gr.Markdown("### 校对选项")
            api_provider_selector = gr.Radio(choices=["Google Gemini", "OpenAI"], label="选择 API 提供商", value="Google Gemini")
            model_selector = gr.Radio(label="选择校对模型", choices=initial_google_models, value=initial_google_models[0] if initial_google_models else None)
            
            # <--- 修改：使用动态加载的 prompt 列表 ---
            prompt_selector = gr.Radio(
                choices=prompt_choices,
                label="选择校对模式",
                value=prompt_choices[0] if prompt_choices else None
            )

            # <--- 新增：Temperature 滑块 ---
            temperature_slider = gr.Slider(
                minimum=0.0, maximum=1.0, step=0.1, value=0.2,
                label="Temperature (值越低越精确)",
                info="控制输出的确定性。校对任务推荐 0.1-0.3"
            )

            submit_btn = gr.Button("🚀 开始校对", variant="primary")

        with gr.Column(scale=3):
            output_text = gr.Textbox(lines=28, label="校对报告 (实时更新)", placeholder="校对建议将在这里逐章显示...", interactive=False)
            download_file = gr.File(interactive=False, visible=False)

    api_provider_selector.change(fn=update_model_choices, inputs=api_provider_selector, outputs=model_selector)
    
    # <--- 修改：为 click 事件增加 temperature_slider 输入 ---
    submit_btn.click(
        fn=process_and_proofread_novel,
        inputs=[input_text, api_provider_selector, model_selector, prompt_selector, temperature_slider],
        outputs=[output_text, download_file]
    )

    gr.Markdown("---")
    gr.Markdown("开发 by Gemini & AI。")

# --- 5. 启动应用 ---
if __name__ == "__main__":
    required_files = ["config.yaml", "config_gpt.yaml", "models.yaml", "prompts"]
    if all(os.path.exists(f) for f in required_files) and os.path.isdir("prompts") and len(os.listdir("prompts")) > 0:
        print("启动 Gradio 应用... 请在浏览器中打开提供的 URL。")
        app.launch()
    else:
        print("[FATAL] 缺少必要的配置文件或 prompts 文件夹为空。请确保以下存在且 prompts 不为空:")
        for f in required_files: print(f" - {f}")
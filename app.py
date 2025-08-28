# novel_proofreader.py

import gradio as gr
import google.generativeai as genai
import yaml
import re
import os
import time
from datetime import datetime

# --- 1. 加载配置 ---
def load_config():
    """从 config.yaml 文件加载配置"""
    print("[DEBUG] 正在尝试加载 config.yaml...")
    try:
        with open("config.yaml", "r", encoding="utf-8") as file:
            config = yaml.safe_load(file)
            print("[DEBUG] config.yaml 加载成功。")
            return config
    except FileNotFoundError:
        print("[ERROR] 错误：找不到 config.yaml 文件。")
        raise FileNotFoundError(
            "错误：找不到 config.yaml 文件。\n"
            "请在脚本同目录下创建 config.yaml 文件，并填入您的 API_KEY。"
        )
    except Exception as e:
        print(f"[ERROR] 读取 config.yaml 时出错: {e}")
        raise IOError(f"读取 config.yaml 时出错: {e}")

# --- 2. 调用 Gemini API 进行校对 (已集成重试功能) ---
def proofread_chapter_with_gemini(chapter_title, chapter_content, model_name, api_key, prompt_template, proxy_url=None):
    """
    使用指定的 Gemini 模型和 prompt 模板对单个章节进行校对。
    如果 API 调用失败，会自动重试最多2次。
    """
    if proxy_url:
        print(f"[DEBUG] 检测到代理配置，正在为本次 API 调用设置 https_proxy: {proxy_url}")
        os.environ['https_proxy'] = proxy_url
    else:
        if 'https_proxy' in os.environ: del os.environ['https_proxy']

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        return f"无法配置或初始化 Gemini 模型: {e}\n请检查您的 API Key 是否正确。"

    prompt = prompt_template.format(chapter_title=chapter_title, chapter_content=chapter_content)

    # ==================== 新增的重试逻辑 ====================
    max_retries = 2
    retry_delay = 3 # 秒

    try:
        for attempt in range(max_retries + 1):
            try:
                print(f"[DEBUG] 正在为章节 '{chapter_title}' 调用 Gemini API (模型: {model_name}, 尝试: {attempt + 1}/{max_retries + 1})...")
                response = model.generate_content(prompt)
                print(f"[DEBUG] 已收到来自 API 的章节 '{chapter_title}' 的响应。")
                return response.text # 成功，直接返回结果并退出函数

            except Exception as e:
                print(f"[ERROR] 尝试 {attempt + 1} 失败: {e}")
                if attempt < max_retries:
                    print(f"[INFO] {retry_delay} 秒后进行重试...")
                    time.sleep(retry_delay)
                else:
                    # 所有重试均告失败
                    print(f"[ERROR] 所有 {max_retries + 1} 次尝试均失败。")
                    error_msg = f"在处理章节 '{chapter_title}' 时调用 API 出错 (已重试 {max_retries} 次)。\n最后错误: {e}\n请检查网络连接、API Key权限、代理设置或模型名称是否正确。"
                    return error_msg
    finally:
        # 无论成功还是失败，最后都清理代理设置
        if 'https_proxy' in os.environ:
            del os.environ['https_proxy']
            print("[DEBUG] 已清理本次 API 调用的 https_proxy 设置。")
    # ========================================================

# --- 3. 主处理函数 (移除进度条，增加 prompt 选择) ---
def process_and_proofread_novel(novel_text, model_name, prompt_mode): # <--- 移除了 progress，增加了 prompt_mode
    """
    分割小说文本，逐章校对，并以流式方式返回结果。
    """
    print("\n--- 开始新的校对任务 ---")
    if not novel_text.strip():
        print("[INFO] 输入文本为空。")
        yield "请输入小说内容。", gr.File(visible=False)
        return

    # --- 加载 Prompt 模板 ---
    prompt_filepath = f"prompts/{prompt_mode}.txt"
    print(f"[DEBUG] 正在加载 prompt 模板: {prompt_filepath}")
    try:
        with open(prompt_filepath, "r", encoding="utf-8") as f:
            prompt_template = f.read()
        print("[DEBUG] Prompt 模板加载成功。")
    except FileNotFoundError:
        error_msg = f"错误：找不到 prompt 文件 '{prompt_filepath}'。请确保 prompts 文件夹及文件存在。"
        print(f"[ERROR] {error_msg}")
        yield error_msg, gr.File(visible=False)
        return

    try:
        config = load_config()
        api_key = config.get("API_KEY")
        proxy_url = config.get("BASE_URL")
        # 简单的代理URL格式化
        if proxy_url and not proxy_url.startswith(('http://', 'https://')):
            proxy_url = "http://" + proxy_url.split("://")[-1].replace("/v1", "")

        if not api_key or "XXXXXX" in api_key or "YOUR_GEMINI_API_KEY" in api_key:
            yield "错误: API_KEY 未在 config.yaml 中配置。", gr.File(visible=False)
            return
    except (FileNotFoundError, IOError) as e:
        yield str(e), gr.File(visible=False)
        return

    chapters_raw = re.split(r'^(第.*?章)', novel_text, flags=re.MULTILINE)
    
    chapter_list = []
    preamble = chapters_raw[0].strip()
    if preamble:
        chapter_list.append({"title": "【序章/前言】", "content": preamble})

    remaining_chapters = chapters_raw[1:]
    for i in range(0, len(remaining_chapters), 2):
        if i + 1 < len(remaining_chapters):
            title = remaining_chapters[i].strip()
            content = remaining_chapters[i+1].strip()
            if content:
                chapter_list.append({"title": title, "content": content})
    
    if not chapter_list and novel_text.strip():
        chapter_list.append({"title": "【全文】", "content": novel_text.strip()})

    if not chapter_list:
        yield "未能解析出任何文本内容。", gr.File(visible=False)
        return

    print(f"[DEBUG] 分割完成，共找到 {len(chapter_list)} 个部分需要处理。")

    full_report = f"小说校对报告 ({prompt_mode} 模式)\n"
    full_report += f"模型: {model_name}\n"
    full_report += "====================\n\n"
    
    yield full_report, gr.File(visible=False)

    for i, chapter in enumerate(chapter_list):
        print(f"[INFO] 开始处理第 {i+1}/{len(chapter_list)} 部分: {chapter['title']}")
        full_report += f"{i+1}/{len(chapter_list)}: {chapter['title']}\n"
        yield full_report, gr.File(visible=False)
        result = proofread_chapter_with_gemini(
            chapter['title'], 
            chapter['content'], 
            model_name, 
            api_key,
            prompt_template, # <--- 传递 prompt 模板
            proxy_url
        )
        
        full_report += result + "\n\n--------------------\n\n"
        
        print(f"[STREAM] 正在更新界面，显示章节 '{chapter['title']}' 的结果。")
        yield full_report, gr.File(visible=False)
        
        time.sleep(1)
    full_report += "小说校对完毕\n\n"
    print("[INFO] 所有章节校对完成。")

    # --- 带时间戳的文件名 ---
    timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    output_filename = f"report_{timestamp}.txt"
    
    print(f"[DEBUG] 正在将最终报告写入文件: {output_filename}")
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(full_report)
        print("[INFO] 报告文件写入成功。")
        yield full_report, gr.File(value=output_filename, visible=True, label=f"下载报告 ({output_filename})")
    except Exception as e:
        print(f"[ERROR] 写入报告文件时出错: {e}")
        yield full_report + f"\n\n错误：无法创建下载文件: {e}", gr.File(visible=False)
    
    print("--- 校对任务结束 ---\n")


# --- 4. Gradio 界面 (重大更新) ---
with gr.Blocks(theme=gr.themes.Soft()) as app:
    gr.Markdown("# 📖 小说文本智能校对器 (Gemini)")
    gr.Markdown("将你的小说文本粘贴到下方，工具会自动按 **每行开头的“第X章”** 进行分割，并调用 Gemini API 逐章进行校对。")
    
    with gr.Row():
        with gr.Column(scale=2):
            input_text = gr.Textbox(
                lines=20,
                label="小说原文",
                placeholder="请在这里粘贴你的小说全文..."
            )
            
            gr.Markdown("### 校对选项")
            prompt_selector = gr.Radio(
                choices=[("综合审查 (语句+错字)", "detailed_review"), ("仅查错别字", "simple_typo")],
                label="选择校对模式",
                value="detailed_review"
            )

            model_selector = gr.Radio(
                # <--- 更新模型名称 ---
                ["gemini-2.5-flash", "gemini-2.5-pro"],
                label="选择校对模型",
                value="gemini-2.5-flash"
            )

            submit_btn = gr.Button("🚀 开始校对", variant="primary")

        with gr.Column(scale=3):
            output_text = gr.Textbox(
                lines=28, # 增加行数以更好地显示内容
                label="校对报告 (实时更新)",
                placeholder="校对建议将在这里逐章显示...",
                interactive=False
            )
            download_file = gr.File(
                interactive=False,
                visible=False # 初始状态下隐藏
            )

    submit_btn.click(
        fn=process_and_proofread_novel,
        inputs=[input_text, model_selector, prompt_selector], # <--- 增加了 prompt_selector
        outputs=[output_text, download_file]
    )

    gr.Markdown("---")
    gr.Markdown("开发 by Gemini & AI。")


# --- 5. 启动应用 ---
if __name__ == "__main__":
    if not os.path.exists("prompts"):
        print("错误：找不到 'prompts' 文件夹。请创建该文件夹并添加提示词 .txt 文件。")
    elif not os.path.exists("config.yaml"):
        print("错误：找不到 config.yaml 文件。请先创建并配置该文件。")
    else:
        print("启动 Gradio 应用... 请在浏览器中打开提供的 URL。")
        print("在下方终端窗口查看 [DEBUG] 和 [ERROR] 信息。")
        app.launch()
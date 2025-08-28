# Gemini_Novel_Proofreader
Use gemini api to proof read chinese novels
使用Gemini api快速校对中长篇文章文本，按章节分割、校对。

## 🚀 快速开始

请按照以下步骤在您的本地计算机上运行本项目。

### 1. 先决条件

*   已安装 [Python 3.9](https://www.python.org/downloads/) 或更高版本。
*   拥有一个 [Google Gemini API Key](https://aistudio.google.com/app/apikey)。

### 2. 安装步骤

1.  **克隆仓库**
    ```bash
    git clone https://github.com/asasasasasbc/Gemini_Novel_Proofreader/Gemini-Novel-Proofreader.git
    cd Gemini-Novel-Proofreader
    ```

2.  **安装依赖**
    建议创建一个虚拟环境。
    ```bash
    # (可选) 创建并激活虚拟环境
    python -m venv venv
    source venv/bin/activate  # on Windows use `venv\Scripts\activate`

    # 安装所有必需的库
    pip install -r requirements.txt
    ```

3.  **配置 API Key**
    *   将 `config.yaml.template` (如果提供) 或手动创建一个名为 `config.yaml` 的文件。
    *   打开 `config.yaml` 并填入您的信息：
    ```yaml
    # 你的 Google Gemini API Key
    API_KEY: "...YOUR_API_KEY..."

    # 如果你需要通过代理访问 API, 请填写你的代理地址
    # 示例: BASE_URL: "http://127.0.0.1:7890"
    BASE_URL: ""
    ```
    **重要**: 请确保不要将含有您个人密钥的 `config.yaml` 文件上传到公开的 Git 仓库中！

### 3. 运行应用

一切就绪后，在终端中运行以下命令：

```bash
python app.py
```

终端会输出一个本地 URL (例如 `http://127.0.0.1:7860`)。在您的浏览器中打开此链接即可开始使用

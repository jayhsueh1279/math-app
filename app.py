import io
import os
import time  # 👈 新增：時間控制模組
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify
from PIL import Image
from google.api_core.exceptions import ResourceExhausted # 👈 新增：專門捕捉 429 錯誤

app = Flask(__name__)

# ==========================================
# 👇 請確認這裡有您的 API Key
# ==========================================
raw_api_key = """
AIzaSyCxqPXShw1zg2wjdtoaOEoQlmkP_S36WlM
"""

# 1. 設定與清理 API Key
MY_API_KEY = os.environ.getgenai.configure(api_key=MY_API_KEY)

# 2. 自動模型選擇系統
print("🔍 正在自動搜尋您的可用模型...")
selected_model = None

try:
    all_models = list(genai.list_models())
    valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
    
# 優先找 1.5 flash (額度較高，不易報錯)
    for m_name in valid_models:
        if "gemini-1.5-flash" in m_name:  # <--- 改成 1.5
            selected_model = m_name
            break
    
    if not selected_model:
        for m_name in valid_models:
            if "flash" in m_name and "latest" not in m_name:
                selected_model = m_name
                break

    if not selected_model and valid_models:
        selected_model = valid_models[0]

    if selected_model:
        print(f"✅ 成功選定模型: {selected_model}")
        model = genai.GenerativeModel(selected_model)
    else:
        print("❌ 錯誤：找不到可用模型")
        model = None

except Exception as e:
    print(f"⚠️ 模型搜尋發生錯誤: {e}")
    model = genai.GenerativeModel('gemini-pro')

# 3. 數學算式清理工具
def clean_equation_for_graphing(latex_str):
    clean = latex_str.replace("```latex", "").replace("```", "").strip()
    if "=" in clean:
        clean = clean.split("=")[-1]
    
    clean = clean.replace(r"\left", "").replace(r"\right", "")
    clean = clean.replace(r"\mathrm", "").replace(r"\text", "")
    clean = clean.replace(r"\sin", "sin").replace(r"\cos", "cos").replace(r"\tan", "tan")
    clean = clean.replace(r"\sqrt", "sqrt")
    clean = clean.replace(r"\log", "log").replace(r"\ln", "log")
    
    # 強制修復黏在一起的變數
    clean = clean.replace("sinx", "sin(x)").replace("cosx", "cos(x)").replace("tanx", "tan(x)")
    
    clean = clean.replace(r"\pi", "PI").replace("pi", "PI")
    clean = clean.replace(r"\theta", "x").replace("theta", "x")
    
    clean = clean.replace(r"\frac", "")
    clean = clean.replace(r"^{", "^(").replace(r"}", ")") 
    clean = clean.replace(r"{", "(").replace(r"}", ")")   
    clean = clean.replace(r"\cdot", "*")
    clean = clean.replace("×", "*").replace("÷", "/")
    
    return clean.strip()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    if not model:
        return jsonify({'error': '後端未連接模型'}), 500

    if 'image' not in request.files:
        return jsonify({'error': '未上傳圖片'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': '未選擇檔案'}), 400
    
    try:
        image = Image.open(io.BytesIO(file.read()))
        prompt = "你是一個數學 OCR 專家。請辨識圖片中的函數算式，只輸出純 LaTeX 格式 (例如 y=x^2)，不要其他文字。"
        
        # 🔥【重點新增】自動重試機制 (解決 429 錯誤)
        max_retries = 3
        latex_result = ""
        
        for attempt in range(max_retries):
            try:
                response = model.generate_content([prompt, image])
                latex_result = response.text.strip()
                break # 成功就跳出迴圈
            except ResourceExhausted:
                # 如果遇到 429 錯誤
                print(f"⚠️ 請求過多 (429)，正在冷卻 {2 * (attempt + 1)} 秒...")
                time.sleep(2 * (attempt + 1)) # 第一次等2秒，第二次等4秒...
                if attempt == max_retries - 1:
                    return jsonify({'error': '伺服器忙碌中 (429)，請休息 1 分鐘後再試'}), 429
            except Exception as e:
                raise e # 其他錯誤直接報錯

        graph_fn = clean_equation_for_graphing(latex_result)
        return jsonify({'success': True, 'latex': latex_result, 'graph_fn': graph_fn})

    except Exception as e:
        print(f"錯誤: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    print("🚀 網站啟動中...")
    app.run(debug=True, port=5000)
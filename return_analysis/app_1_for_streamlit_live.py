import streamlit as st
import pandas as pd
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
import os  

# ==========================================
# 0. PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Style Return Analyzer", page_icon="📊", layout="wide")
st.title("🛒 E-Commerce Style Level Return Analyzer")

# ==========================================
# 1. SECURE API SETUP
# ==========================================
try:
    YOUR_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    st.error("⚠️ API Key not found! Please set GEMINI_API_KEY in .streamlit/secrets.toml")
    st.stop()

genai.configure(api_key=YOUR_API_KEY)
MODEL_NAME = 'gemini-2.5-flash' 
model = genai.GenerativeModel(MODEL_NAME)

@retry(
    stop=stop_after_attempt(3), 
    wait=wait_exponential(multiplier=1, min=2, max=6), 
    reraise=True
)
def call_gemini_api(prompt_text):
    response = model.generate_content(prompt_text)
    return response.text

# ==========================================
# 2. DATA LOADING
# ==========================================
@st.cache_resource
def load_data():
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        earn_more_path = os.path.join(current_dir, "earn_more.xlsx")
        fk_mars_path = os.path.join(current_dir, "fk_mars_return.xlsx")

        sales_needed_cols = ['SKU ID', 'Style Code', 'Group Code', 'Gross Units', 'GMV']
        
        sales_df = pd.read_excel(
            earn_more_path, 
            usecols=lambda c: c in sales_needed_cols
        )
        sales_df = sales_df.rename(columns={'SKU ID': 'SKU'})

        full_returns_df = pd.read_excel(
            fk_mars_path, 
            usecols=lambda c: c in ['SKU', 'Comments', 'Quantity']
        )
        
        # Merge ebong null comments remove
        df = pd.merge(full_returns_df, sales_df, on='SKU', how='left')
        df_with_comments = df.dropna(subset=['Comments'])
        
        return sales_df, df_with_comments, full_returns_df
    except Exception as e:
        st.error(f"❌ Excel File Load Error: {e}")
        return None, None, None

sales_df, df_with_comments, full_returns_df = load_data()

# ==========================================
# 3. INTERACTIVE UI (By Style Code)
# ==========================================
if df_with_comments is not None:
    st.markdown("### 🔍 Select Product Style to Analyze")
    
    col1, col2 = st.columns(2)
    
    with col1:
        group_options = ["-- Select --"] + df_with_comments['Group Code'].dropna().unique().tolist()
        selected_group = st.selectbox("Group Code:", group_options)

    with col2:
        if selected_group != "-- Select --":
            style_options = ["-- Select --"] + df_with_comments[df_with_comments['Group Code'] == selected_group]['Style Code'].dropna().unique().tolist()
        else:
            style_options = ["-- Select --"]
        selected_style = st.selectbox("Style Code:", style_options)

    # ==========================================
    # 4. METRICS & ANALYSIS ACTION
    # ==========================================
    st.markdown("---")
    
    if st.button("⚡ Get Style Metrics & AI Solution", type="primary", use_container_width=True):
        if selected_style == "-- Select --":
            st.warning("⚠️ Please select a valid Style Code from the dropdowns first!")
        else:
            with st.spinner("⏳ Analyzing Data & Consulting Gemini..."):
                
                # 1. Sales Metrics for the entire Style Code
                style_sales_data = sales_df[sales_df['Style Code'] == selected_style]
                if not style_sales_data.empty:
                    gross_units = int(style_sales_data['Gross Units'].sum())
                    total_gmv = float(style_sales_data['GMV'].sum())
                    # Get all SKUs belonging to this style
                    style_skus = style_sales_data['SKU'].unique()
                else:
                    gross_units, total_gmv, style_skus = 0, 0.0, []

                # 2. Return Metrics for the entire Style Code
                if len(style_skus) > 0:
                    style_return_data = full_returns_df[full_returns_df['SKU'].isin(style_skus)]
                    return_units = int(style_return_data['Quantity'].sum())
                else:
                    return_units = 0
                
                return_percentage = round((return_units / gross_units) * 100, 2) if gross_units > 0 else 0
                
                # Display 4 Metrics
                st.markdown("### 📊 Key Metrics (Style Level)")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric(label="Gross Units", value=f"{gross_units}")
                m2.metric(label="Gross Sale (₹)", value=f"₹{total_gmv:,.2f}")
                m3.metric(label="Return Units", value=f"{return_units}", delta_color="inverse")
                m4.metric(label="Return Rate", value=f"{return_percentage}%", delta_color="inverse")
                
                # 3. Extract Comments paired with SKU names
                target_data = df_with_comments[df_with_comments['Style Code'] == selected_style]
                
                st.markdown("### 💡 AI Actionable Solution (Variant Specific)")
                
                if target_data.empty:
                    st.info("⚠️ No customer return text comments found for this Style Code.")
                else:
                    # Creating "SKU -> Comment" pairs so Gemini knows which variant has what issue
                    comments_text = "\n".join([f"- SKU: {row['SKU']} | Comment: {row['Comments']}" for _, row in target_data.iterrows()])
                    
                    prompt = f"""
                    Analyze these customer return feedbacks for the clothing Style Code '{selected_style}'.
                    The feedbacks are mapped to specific SKUs (which contain size/color information).
                    
                    Your tasks:
                    1. Identify the core issues tied to specific variants (e.g., sizes or colors).
                    2. Provide a short, actionable summary pointing out the exact issues for specific variants (e.g., "Size 14 is too short, Size 12 is too long").
                    3. Do not include intro text. Output a 2-3 line concise summary highlighting variant-specific problems and a quick recommendation.

                    User Feedbacks by SKU:
                    {comments_text}
                    """
                    
                    try:
                        raw_response = call_gemini_api(prompt)
                        st.success(f"**Analysis:** {raw_response.strip()}")
                            
                    except Exception as e:
                        st.error(f"❌ API Request Failed: {e}")
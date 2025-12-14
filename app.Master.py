import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from wordcloud import WordCloud
from collections import Counter, defaultdict
import re
import time
import platform
import os

# 라이브 크롤링 라이브러리
from selenium import webdriver
from selenium.webdriver.common.by import By
# ### [수정/Modified] Service 모듈 추가 ###
from selenium.webdriver.chrome.service import Service 
import chromedriver_autoinstaller

# ---------------------------------------------------------
# 1. 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="Global Research Trend Tracker",
    page_icon="🧬",
    layout="wide"
)

# 한글 폰트 설정
if platform.system() == 'Darwin': # Mac
    plt.rc('font', family='AppleGothic')
else: # Windows
    plt.rc('font', family='Malgun Gothic')
plt.rc('axes', unicode_minus=False)

# ---------------------------------------------------------
# 2. 세션 스테이트 초기화
# ---------------------------------------------------------
if 'user_excludes' not in st.session_state:
    st.session_state.user_excludes = [
        'analysis', 'study', 'method', 'using', 'based', 'data', 'journal',
        'and', 'the', 'for', 'from', 'with', 'between', 'during', 'review',
        'research', 'results', 'model', 'approach', 'effect', 'response',
        'potential', 'application', 'development'
    ]

if 'crawled_df' not in st.session_state:
    st.session_state.crawled_df = None

if 'current_search_keyword' not in st.session_state:
    st.session_state.current_search_keyword = ""

# ---------------------------------------------------------
# 3. 함수 정의
# ---------------------------------------------------------
def get_saved_files():
    files = [f.replace('_data.csv', '') for f in os.listdir('.') if f.endswith('_data.csv')]
    return sorted(files)

def load_csv_data(crop_name):
    file_path = f"{crop_name}_data.csv"
    try:
        df = pd.read_csv(file_path)
        if 'Views' not in df.columns:
            df['Views'] = 1 
        return df
    except FileNotFoundError:
        return None

def crawl_live_data(keyword):
    driver = None
    status_placeholder = st.empty()

    try:
        # ### [수정/Modified] 드라이버 설정 로직 전체 변경 ###
        options = webdriver.ChromeOptions()
        
        # 1. Headless 모드 활성화 (서버 환경 필수)
        options.add_argument("--headless") 
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        
        # 2. User-Agent 설정 (봇 탐지 우회)
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--window-size=1920,1080")

        # 3. 운영체제(OS)에 따른 드라이버 경로 설정
        if platform.system() == 'Linux':
            # Streamlit Cloud (Linux) 환경
            # packages.txt에 의해 설치된 경로를 지정
            options.binary_location = "/usr/bin/chromium"
            service = Service(executable_path="/usr/bin/chromedriver")
            driver = webdriver.Chrome(service=service, options=options)
            print("✅ Linux 환경(Streamlit Cloud) 감지: 시스템 드라이버 사용")
        else:
            # 로컬(Windows/Mac) 환경
            # 기존처럼 autoinstaller 사용
            chromedriver_autoinstaller.install()
            driver = webdriver.Chrome(options=options)
            print("✅ 로컬 환경 감지: Autoinstaller 드라이버 사용")
        
        # ---------------------------------------------------------
        
        url = f"https://www.mdpi.com/search?q={keyword}" 
        driver.get(url)
        
        msg = f"⏳ 페이지 로딩 중... '{keyword}' 검색 (약 5초 대기)"
        print(msg) 
        status_placeholder.info(msg)
        time.sleep(5) 
        
        is_new_version = False
        try:
            if "new version of our website" in driver.page_source.lower():
                is_new_version = True
                print("🚨 감지됨: 사이트가 'New Version'입니다.")
        except:
            pass

        articles = driver.find_elements(By.CLASS_NAME, "generic-item")
        print(f"DEBUG: 'generic-item' 개수: {len(articles)}")

        if is_new_version or len(articles) == 0:
            # Headless 모드에서는 '클릭' 유도가 불가능하므로, 바로 다른 태그를 찾거나 대기만 수행
            print("🚨 구조 변경 감지 또는 로딩 지연. 추가 대기 및 태그 탐색 시도.")
            
            for i in range(5, 0, -1):
                check_articles = driver.find_elements(By.CLASS_NAME, "generic-item")
                if len(check_articles) > 0:
                    status_placeholder.success("✅ 데이터 로딩 확인!")
                    articles = check_articles
                    break 
                time.sleep(1)
            
            if len(articles) == 0:
                print("DEBUG: 구 버전 감지 실패. 신규 구조(article-item) 탐색 시도.")
                articles = driver.find_elements(By.CLASS_NAME, "article-item")

        print(f"최종 발견된 요소 수: {len(articles)}")
        
        data = []
        garbage_keywords = ["Sign in", "Update Search", "Publication Date", "Show export options", "Unknown", "Subscribe"]

        for art in articles:
            try:
                try:
                    title_elem = art.find_element(By.CLASS_NAME, "title-link")
                except:
                    try:
                        title_elem = art.find_element(By.TAG_NAME, "a")
                    except:
                        continue
                
                title = title_elem.text.strip()
                
                if not title or len(title) < 20:
                    continue
                if any(bad_word in title for bad_word in garbage_keywords):
                    continue

                try:
                    authors = art.find_element(By.CLASS_NAME, "authors").text
                except:
                    authors = "Unknown"
                
                if not authors or authors == "Unknown":
                    continue

                full_text = art.text
                view_match = re.search(r"(?:Viewed by|Views)[:\s]*([\d,]+)", full_text)
                if view_match:
                    views = int(view_match.group(1).replace(",", ""))
                else:
                    views = 1 

                data.append([keyword, title, authors, views])
            except Exception as e:
                continue
        
        status_placeholder.empty()
        
    except Exception as e:
        err_msg = f"크롤링 시스템 에러: {e}"
        print(err_msg)
        st.error(err_msg)
        return pd.DataFrame()
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        
    if data:
        return pd.DataFrame(data, columns=['Keyword', 'Title', 'Authors', 'Views'])
    else:
        return pd.DataFrame()

# ---------------------------------------------------------
# 4. 사이드바 UI
# ---------------------------------------------------------
st.sidebar.header("🔍 분석 컨트롤 패널")

data_source = st.sidebar.radio(
    "데이터 소스",
    ("📂 저장된 파일(CSV)", "🌐 실시간 검색(Live)")
)

if data_source == "📂 저장된 파일(CSV)":
    saved_files = get_saved_files()
    if saved_files:
        crop_option = st.sidebar.selectbox("저장된 데이터 선택", saved_files)
        if st.session_state.current_search_keyword != crop_option:
            df = load_csv_data(crop_option)
            st.session_state.crawled_df = df
            st.session_state.current_search_keyword = crop_option
    else:
        st.sidebar.warning("저장된 파일이 없습니다.")

else: # 라이브 모드
    live_keyword = st.sidebar.text_input("검색 키워드", "Smart Farm")
    
    if st.sidebar.button("🚀 검색 시작"):
        st.session_state.crawled_df = None 
        
        with st.spinner(f"MDPI에서 '{live_keyword}' 관련 데이터를 수집 중입니다..."):
            df = crawl_live_data(live_keyword)
            if not df.empty:
                st.session_state.crawled_df = df
                st.session_state.current_search_keyword = live_keyword
                st.success(f"수집 완료! ({len(df)}건)")
            else:
                st.error("데이터를 찾지 못했습니다. (수동 전환 실패 또는 데이터 없음)")

    if st.session_state.crawled_df is not None and not st.session_state.crawled_df.empty:
        
        # 1. 데이터프레임을 CSV 문자열로 변환 (한글 깨짐 방지 utf-8-sig)
        csv_data = st.session_state.crawled_df.to_csv(index=False).encode('utf-8-sig')

        # 2. 저장하기 버튼 대신 '다운로드 버튼' 생성
        filename = f"{st.session_state.current_search_keyword}_data.csv"
        
        st.sidebar.download_button(
            label="💾 결과 컴퓨터로 다운로드",
            data=csv_data,
            file_name=filename,
            mime='text/csv'
        )

st.sidebar.markdown("---")

# 제외 단어 관리
st.sidebar.subheader("🚫 제외 단어 관리")
col_add1, col_add2 = st.sidebar.columns([3, 1])
with col_add1:
    new_stopword = st.text_input("단어 추가 (쉼표로 구분 가능)", placeholder="예: review, analysis, data", label_visibility="collapsed")
with col_add2:
    if st.button("추가"):
        if new_stopword:
            new_words = [word.strip().lower() for word in new_stopword.split(',')]
            added_count = 0
            for word in new_words:
                if word and word not in st.session_state.user_excludes:
                    st.session_state.user_excludes.append(word)
                    added_count += 1
            
            if added_count > 0:
                st.rerun()

if st.sidebar.button("🔄 제외 단어 초기화"):
    st.session_state.user_excludes = [
        'analysis', 'study', 'method', 'using', 'based', 'data', 'journal',
        'and', 'the', 'for', 'from', 'with', 'between', 'during', 'review',
        'research', 'results', 'model', 'approach', 'effect', 'response',
        'potential', 'application', 'development'
    ]
    st.rerun()

current_excludes = st.sidebar.multiselect(
    "현재 제외된 단어들 (x 눌러 삭제)",
    options=st.session_state.user_excludes,
    default=st.session_state.user_excludes
)

if set(current_excludes) != set(st.session_state.user_excludes):
    st.session_state.user_excludes = current_excludes
    st.rerun()

# ---------------------------------------------------------
# 5. 메인 대시보드
# ---------------------------------------------------------
final_df = st.session_state.crawled_df
keyword_display = st.session_state.current_search_keyword

st.title(f"🧬 Global Research Trends: {keyword_display if keyword_display else '...'}")

if final_df is not None and not final_df.empty:
    
    # 탭 메뉴
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 빈도수 트렌드", "👁️ 조회수 트렌드", "🔗 상관분석", "🧑‍🔬 주요 연구자", "📄 리스트"])

    # 데이터 전처리
    all_titles = final_df['Title'].astype(str).tolist()
    if 'Views' not in final_df.columns:
        final_df['Views'] = 1
    
    final_df['Views'] = final_df['Views'].fillna(1).replace(0, 1)
    all_views = final_df['Views'].tolist()
    
    final_stop_words = set(st.session_state.user_excludes)
    if keyword_display:
        split_keywords = keyword_display.lower().split()
        final_stop_words.update(split_keywords)

    weighted_word_counts = defaultdict(int) 
    simple_word_counts = defaultdict(int)   

    for title, view_count in zip(all_titles, all_views):
        words_in_title = re.findall(r'\b[a-zA-Z]{3,}\b', title.lower())
        for w in words_in_title:
            if w not in final_stop_words:
                weighted_word_counts[w] += view_count 
                simple_word_counts[w] += 1            

    # === [Tab 1] 단순 빈도수 트렌드 ===
    with tab1:
        st.markdown("### 📊 Basic Frequency WordCloud")
        st.caption("조회수와 상관없이, 논문 제목에 **가장 많이 등장한 키워드**입니다.")

        if len(simple_word_counts) > 0:
            col1, col2 = st.columns([1.2, 1])
            with col1:
                wc_simple = WordCloud(width=800, height=500, background_color='white', colormap='viridis').generate_from_frequencies(simple_word_counts)
                fig_wc, ax = plt.subplots()
                ax.imshow(wc_simple, interpolation='bilinear')
                ax.axis('off')
                st.pyplot(fig_wc)

            with col2:
                st.markdown("#### 🏆 Top Frequency Keywords")
                top_10_simple = sorted(simple_word_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                
                if top_10_simple:
                    top_words = [item[0] for item in top_10_simple]
                    top_scores = [item[1] for item in top_10_simple]
                    
                    fig_bar, ax = plt.subplots(figsize=(5, 4))
                    ax.barh(top_words[::-1], top_scores[::-1], color='#4CAF50') 
                    ax.set_xlabel('Frequency (Count)')
                    st.pyplot(fig_bar)
        else:
            st.info("⚠️ 분석할 단어가 없습니다.")

    # === [Tab 2] 조회수 기반 트렌드 ===
    with tab2:
        st.markdown("### 👁️ Impact WordCloud (Weighted by Views)")
        st.caption("사람들이 **실제로 많이 조회한 논문**의 키워드를 더 크게 보여줍니다.")
        
        if len(weighted_word_counts) > 0 and max(weighted_word_counts.values()) > 0:
            col1, col2 = st.columns([1.2, 1])
            with col1:
                try:
                    wc_weighted = WordCloud(width=800, height=500, background_color='white', colormap='magma').generate_from_frequencies(weighted_word_counts)
                    fig_wc, ax = plt.subplots()
                    ax.imshow(wc_weighted, interpolation='bilinear')
                    ax.axis('off')
                    st.pyplot(fig_wc)
                except Exception as e:
                    st.error(f"워드클라우드 생성 중 오류: {e}")

            with col2:
                st.markdown("#### 🏆 High Impact Keywords")
                top_10_weighted = sorted(weighted_word_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                
                if top_10_weighted:
                    top_words = [item[0] for item in top_10_weighted]
                    top_scores = [item[1] for item in top_10_weighted]
                    
                    fig_bar, ax = plt.subplots(figsize=(5, 4))
                    ax.barh(top_words[::-1], top_scores[::-1], color='#e17055') 
                    ax.set_xlabel('Total Views')
                    st.pyplot(fig_bar)
        else:
            st.warning("⚠️ 조회수 데이터가 충분하지 않아 가중치 분석을 할 수 없습니다.")

    # === [Tab 3] 상관관계 분석 ===
    with tab3:
        st.markdown("#### 🔗 키워드 동시 출현 상관관계")
        if len(simple_word_counts) > 1:
            top_keywords = [item[0] for item in sorted(simple_word_counts.items(), key=lambda x: x[1], reverse=True)[:10]]
            
            matrix_data = []
            for title in final_df['Title'].astype(str):
                row = []
                title_lower = title.lower()
                for key in top_keywords:
                    row.append(1 if key in title_lower else 0)
                matrix_data.append(row)
            
            if matrix_data:
                df_matrix = pd.DataFrame(matrix_data, columns=top_keywords)
                corr_matrix = df_matrix.corr().fillna(0)
                
                fig_heat, ax = plt.subplots(figsize=(8, 6))
                sns.heatmap(corr_matrix, annot=True, fmt=".2f", cmap='Blues', ax=ax)
                st.pyplot(fig_heat)
            else:
                st.info("데이터 부족")
        else:
            st.warning("데이터 부족")

    # === [Tab 4] 주요 연구자 ===
    with tab4:
        st.markdown(f"#### 🧑‍🔬 Top Authors Analysis")
        
        author_freq_dict = defaultdict(int)
        author_view_dict = defaultdict(int)
        
        for authors_str, views in zip(final_df['Authors'].astype(str), final_df['Views']):
            authors_str = authors_str.replace("by ", "")
            cleaned = authors_str.replace(" and ", ", ").split(",")
            for name in cleaned:
                name = name.strip()
                if len(name) > 2: 
                    author_freq_dict[name] += 1
                    author_view_dict[name] += views
        
        auth_tab1, auth_tab2 = st.tabs(["📚 논문수 기준 (Quantity)", "🌟 영향력 기준 (Impact)"])
        
        with auth_tab1:
            if author_freq_dict:
                top_authors_freq = sorted(author_freq_dict.items(), key=lambda x: x[1], reverse=True)[:10]
                names = [item[0] for item in top_authors_freq]
                counts = [item[1] for item in top_authors_freq]
                
                fig_a1, ax = plt.subplots(figsize=(8, 4))
                ax.bar(names, counts, color='#ff7675') 
                plt.xticks(rotation=45, ha='right')
                ax.set_title("Most Prolific Authors")
                st.pyplot(fig_a1)
            else:
                st.warning("저자 정보 없음")
        
        with auth_tab2:
            if author_view_dict and max(author_view_dict.values()) > 0:
                top_authors_view = sorted(author_view_dict.items(), key=lambda x: x[1], reverse=True)[:10]
                names = [item[0] for item in top_authors_view]
                views = [item[1] for item in top_authors_view]
                
                fig_a2, ax = plt.subplots(figsize=(8, 4))
                ax.bar(names, views, color='#6c5ce7') 
                plt.xticks(rotation=45, ha='right')
                ax.set_title("Most Impactful Authors")
                st.pyplot(fig_a2)
            else:
                st.info("조회수 데이터 부족")

    # === [Tab 5] 데이터 리스트 ===
    with tab5:
        st.write(f"총 **{len(final_df)}**건의 논문")
        
        final_df_display = final_df.copy()
        final_df_display.index = final_df_display.index + 1
        st.dataframe(final_df_display)

elif data_source == "🌐 실시간 검색(Live)":
    st.info("👈 사이드바에서 키워드를 입력하고 검색해주세요.")

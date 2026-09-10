import datetime
import requests
import pandas as pd
import pytz
import streamlit as st

# Streamlit 페이지 기본 설정
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide"
)

# -----------------------------------------------------------------------------
# 1. 한국 시간(KST) 기준 어제 날짜 구하기 함수
# -----------------------------------------------------------------------------
def get_yesterday_kst():
    """
    배포 서버의 시계와 상관없이 한국 시간(KST)을 기준으로 '어제' 날짜를 YYYYMMDD 형식으로 반환합니다.
    """
    # 한국 표준시(Asia/Seoul) 타임존 설정
    tz_kst = pytz.timezone('Asia/Seoul')
    # 현재 한국 시간 가져오기
    now_kst = datetime.datetime.now(tz_kst)
    # 하루(1일)를 빼서 어제 날짜 계산
    yesterday_kst = now_kst - datetime.timedelta(days=1)
    # YYYYMMDD 형태로 문자열 변환
    return yesterday_kst.strftime('%Y%m%d')


# -----------------------------------------------------------------------------
# 2. KOBIS API 데이터 불러오기 함수 (캐싱 적용)
# -----------------------------------------------------------------------------
# st.cache_data를 적용하여 동일한 날짜 요청 시 API를 다시 호출하지 않고 1시간(3600초) 동안 결과를 기억합니다.
@st.cache_data(ttl=3600)
def fetch_box_office_data(api_key, target_date):
    """
    KOBIS API를 호출하여 해당 날짜의 박스오피스 데이터를 가져옵니다.
    """
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": api_key,
        "targetDt": target_date
    }
    
    # API 요청 (타임아웃 10초 설정)
    response = requests.get(url, params=params, timeout=10)
    
    # HTTP 상태 코드가 200이 아닌 경우 에러 처리
    if response.status_code != 200:
        return None, f"서버 통신에 실패했습니다. (응답 코드: {response.status_code})"
    
    data = response.json()
    
    # 1) 인증키 오류 등으로 인한 faultInfo 반환 확인
    if "faultInfo" in data:
        fault_message = data["faultInfo"].get("message", "알 수 없는 오류")
        return None, f"API 오류가 발생했습니다: {fault_message}"
    
    # 2) 정상 응답 구조 확인
    box_office_result = data.get("boxOfficeResult", {})
    daily_list = box_office_result.get("dailyBoxOfficeList", [])
    
    # 3) 영화 목록이 비어있는 경우 확인
    if not daily_list:
        return None, "해당 날짜의 박스오피스 데이터가 비어있습니다. 아직 집계 전이거나 API 점검 중일 수 있습니다."
    
    return daily_list, None


# -----------------------------------------------------------------------------
# 3. 메인 화면 UI 구성
# -----------------------------------------------------------------------------
def main():
    st.title("🎬 어제의 일별 박스오피스")
    
    # Streamlit Secrets에서 API 키 불러오기
    if "KOBIS_KEY" not in st.secrets:
        st.error("🔑 인증키 설정이 필요합니다!")
        st.info(
            " Streamlit Cloud의 **Secrets** 항목에 `KOBIS_KEY = '발급받은키'` 형태로 인증키를 등록해주세요.\n"
            " 로컬 테스트 시에는 `.streamlit/secrets.toml` 파일에 키를 추가해야 합니다."
        )
        return
    
    api_key = st.secrets["KOBIS_KEY"]
    target_date = get_yesterday_kst()
    
    # 날짜 표시용 포맷팅 (YYYYMMDD -> YYYY-MM-DD)
    formatted_date = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:]}"
    st.write(f"📅 **조회 기준일 (한국 시간 기준 어제):** {formatted_date}")
    st.divider()
    
    # 데이터 불러오기 실행
    data_list, error_message = fetch_box_office_data(api_key, target_date)
    
    # 에러가 발생했거나 데이터가 없는 경우 안내 메시지 출력
    if error_message:
        st.warning("⚠️ 데이터를 불러올 수 없습니다. 아래 내용을 확인해주세요.")
        st.error(error_message)
        st.markdown(
            """
            **🔍 확인 사항:**
            1. `KOBIS_KEY` 인증키가 올바르게 입력되었는지 확인해주세요. (KOBIS 공식 홈페이지에서 발급)
            2. 일일 API 호출 한도(기본 3,000회)를 초과했는지 확인해주세요.
            3. KOBIS 서버 점검 시간일 수 있으니 잠시 후 다시 시도해보세요.
            """
        )
        return

    # -------------------------------------------------------------------------
    # 4. 데이터 전처리 (문자열 -> 숫자 변환)
    # -------------------------------------------------------------------------
    df = pd.DataFrame(data_list)
    
    # 숫자로 다루어야 하는 컬럼들의 타입을 정수(int)형으로 변환
    numeric_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    
    # 순위 기준으로 정렬
    df = df.sort_values(by="rank")

    # -------------------------------------------------------------------------
    # 5. 1위 영화 주요 지표 카드 (Metrics)
    # -------------------------------------------------------------------------
    top_movie = df.iloc[0]
    
    st.subheader(f"🥇 1위 영화: {top_movie['movieNm']}")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="어제 관객수", value=f"{top_movie['audiCnt']:,} 명")
    with col2:
        st.metric(label="누적 관객수", value=f"{top_movie['audiAcc']:,} 명")
    with col3:
        st.metric(label="상영 스크린수", value=f"{top_movie['scrnCnt']:,} 개")
        
    st.divider()

    # -------------------------------------------------------------------------
    # 6. 관객수 상위 5편 막대그래프
    # -------------------------------------------------------------------------
    st.subheader("📊 관객수 상위 5개 영화")
    top5_df = df.head(5)
    
    # Streamlit 기본 막대그래프 활용 (x: 영화명, y: 관객수)
    chart_data = top5_df.set_index("movieNm")[["audiCnt"]]
    chart_data.columns = ["어제 관객수"]
    st.bar_chart(chart_data)

    st.divider()

    # -------------------------------------------------------------------------
    # 7. 박스오피스 전체 순위 표 (Table)
    # -------------------------------------------------------------------------
    st.subheader("📋 박스오피스 전체 순위 (1~10위)")
    
    # 표시할 주요 컬럼 추출 및 이름을 한국어로 변경
    display_df = df[["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
    display_df.columns = ["순위", "영화명", "개봉일", "어제 관객수", "누적 관객수", "스크린수"]
    
    # 숫자 데이터 세자리마다 콤마(,) 추가한 포맷팅 적용
    display_df["어제 관객수"] = display_df["어제 관객수"].apply(lambda x: f"{x:,}")
    display_df["누적 관객수"] = display_df["누적 관객수"].apply(lambda x: f"{x:,}")
    display_df["스크린수"] = display_df["스크린수"].apply(lambda x: f"{x:,}")
    
    # 인덱스 없이 깔끔하게 표로 출력
    st.dataframe(display_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()

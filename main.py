from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# =========================================================
# 기본 설정
# =========================================================
st.set_page_config(
    page_title="민주적 점심",
    page_icon="🍽️",
    layout="centered",
)

# 한국 시간대
KST = ZoneInfo("Asia/Seoul")

# 구글 시트의 열 순서
COLUMNS = ["시각", "팀원", "메뉴", "구분"]

# 메뉴 목록
MENU_OPTIONS = [
    "치킨",
    "피자",
    "족발",
    "중식",
    "초밥",
    "양식",
    "동남아식",
    "한식",
    "분식",
    "국밥",
    "햄버거",
    "샌드위치",
    "샐러드",
    "고기",
    "면요리",
    "기타",
]


# =========================================================
# 화면 디자인
# =========================================================
st.markdown(
    """
    <style>
        .stApp {
            background-color: #fffaf3;
        }

        .main-title {
            text-align: center;
            font-size: 2.4rem;
            font-weight: 800;
            color: #5c4033;
            margin-bottom: 0.2rem;
        }

        .sub-title {
            text-align: center;
            color: #806b5a;
            margin-bottom: 2rem;
        }

        .winner-box {
            background: linear-gradient(135deg, #fff0cf, #ffe0bd);
            border: 2px solid #f0b775;
            border-radius: 20px;
            padding: 25px 20px;
            text-align: center;
            margin: 15px 0 20px 0;
            box-shadow: 0 5px 15px rgba(120, 80, 40, 0.10);
        }

        .winner-label {
            font-size: 1rem;
            color: #8a6543;
            margin-bottom: 7px;
        }

        .winner-menu {
            font-size: 2.5rem;
            font-weight: 900;
            color: #d26336;
        }

        .winner-votes {
            margin-top: 7px;
            color: #765942;
        }

        .warm-message {
            background-color: #fff3df;
            border-left: 5px solid #efa85d;
            border-radius: 8px;
            padding: 13px 15px;
            margin: 10px 0 18px 0;
            color: #654a35;
        }

        div[data-testid="stMetric"] {
            background-color: white;
            border: 1px solid #f0dfcc;
            border-radius: 14px;
            padding: 12px;
        }

        div.stButton > button {
            width: 100%;
            border-radius: 12px;
            font-weight: 700;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 공통 함수
# =========================================================
def get_sheet_url():
    """
    Streamlit 비밀 금고에서 구글 Apps Script 웹 앱 주소를 가져옵니다.
    주소는 보통 /exec 로 끝납니다.
    """
    try:
        sheet_url = st.secrets["SHEET_URL"].strip()
    except (KeyError, FileNotFoundError):
        st.error(
            "비밀 금고에 `SHEET_URL`이 없습니다. "
            "Streamlit Cloud의 Secrets 설정을 확인해주세요."
        )
        st.stop()

    if not sheet_url:
        st.error("`SHEET_URL` 값이 비어 있습니다.")
        st.stop()

    return sheet_url


def empty_dataframe():
    """기록이 없을 때 사용할 빈 표를 만듭니다."""
    return pd.DataFrame(columns=COLUMNS)


def normalize_sheet_data(data):
    """
    구글 Apps Script에서 받은 JSON을 판다스 표로 변환합니다.

    지원하는 형태
    1. 첫 번째 줄이 머리글인 2차원 배열
       [
           ["시각", "팀원", "메뉴", "구분"],
           ["2026-07-23 12:00:00", "홍길동", "치킨", "먹고싶다"]
       ]

    2. 객체 목록
       [
           {"시각": "...", "팀원": "...", "메뉴": "...", "구분": "..."}
       ]
    """
    if data is None:
        return empty_dataframe()

    # Apps Script가 데이터를 다른 키 안에 넣어 보낼 때를 대비합니다.
    if isinstance(data, dict):
        for key in ["data", "rows", "values", "records"]:
            if key in data:
                data = data[key]
                break
        else:
            # 단일 객체 한 건인 경우
            data = [data]

    if not isinstance(data, list) or len(data) == 0:
        return empty_dataframe()

    # 객체 목록인 경우
    if isinstance(data[0], dict):
        df = pd.DataFrame(data)

        # 필요한 열이 빠져 있으면 빈 열을 추가합니다.
        for column in COLUMNS:
            if column not in df.columns:
                df[column] = ""

        return df[COLUMNS].copy()

    # 2차원 배열인 경우
    if isinstance(data[0], list):
        rows = data

        # 첫 줄은 머리글이므로 제외합니다.
        if len(rows) <= 1:
            return empty_dataframe()

        header = [str(value).strip() for value in rows[0]]
        body = rows[1:]

        # 머리글을 이용해 표를 만듭니다.
        try:
            df = pd.DataFrame(body, columns=header)
        except ValueError:
            # 행의 길이가 일정하지 않을 경우 앞의 네 칸만 사용합니다.
            cleaned_rows = []
            for row in body:
                row = list(row[:4])
                row += [""] * (4 - len(row))
                cleaned_rows.append(row)

            df = pd.DataFrame(cleaned_rows, columns=COLUMNS)

        for column in COLUMNS:
            if column not in df.columns:
                df[column] = ""

        return df[COLUMNS].copy()

    return empty_dataframe()


@st.cache_data(ttl=20, show_spinner=False)
def load_records(sheet_url):
    """
    SHEET_URL을 파라미터 없이 열어 전체 기록을 가져옵니다.
    짧은 시간 동안 캐시하여 불필요한 요청을 줄입니다.
    """
    response = requests.get(sheet_url, timeout=15)
    response.raise_for_status()

    data = response.json()
    df = normalize_sheet_data(data)

    if df.empty:
        return empty_dataframe()

    # 빈 행을 제거합니다.
    df = df.fillna("")
    df = df[
        df[COLUMNS]
        .astype(str)
        .apply(lambda row: any(value.strip() for value in row), axis=1)
    ].copy()

    if df.empty:
        return empty_dataframe()

    # 문자열 앞뒤의 공백을 정리합니다.
    for column in COLUMNS:
        df[column] = df[column].astype(str).str.strip()

    # 시트에 저장된 시각은 이미 한국 시간입니다.
    # 따라서 별도의 시간대 변환 없이 문자열을 날짜로 해석합니다.
    df["날짜시간"] = pd.to_datetime(df["시각"], errors="coerce")
    df["날짜"] = df["날짜시간"].dt.date

    # 같은 시간이나 잘못된 시간 문자열이 있어도
    # 시트에 들어온 순서를 확인할 수 있도록 번호를 붙입니다.
    df["_기록순서"] = range(len(df))

    return df


def save_record(sheet_url, member, menu, record_type):
    """
    기록을 구글 Apps Script 웹 앱으로 전송합니다.

    한글이 깨지지 않도록 URL 문자열에 직접 이어붙이지 않고
    requests의 params 기능을 사용합니다.
    """
    params = {
        "member": member,
        "menu": menu,
        "type": record_type,
    }

    response = requests.get(
        sheet_url,
        params=params,
        timeout=15,
    )
    response.raise_for_status()

    return response


def get_today_votes(df, today):
    """
    오늘의 투표만 가져온 뒤,
    같은 팀원이 여러 번 투표했다면 마지막 투표만 남깁니다.
    """
    if df.empty:
        return empty_dataframe()

    today_votes = df[
        (df["구분"] == "먹고싶다")
        & (df["날짜"] == today)
        & (df["팀원"].str.strip() != "")
        & (df["메뉴"].str.strip() != "")
    ].copy()

    if today_votes.empty:
        return today_votes

    # 시각을 해석할 수 없는 기록도 있으므로
    # 최종적으로 시트 기록 순서를 기준으로 마지막 표를 남깁니다.
    today_votes = today_votes.sort_values("_기록순서")
    today_votes = today_votes.drop_duplicates(
        subset=["팀원"],
        keep="last",
    )

    return today_votes


def calculate_winner(today_votes):
    """
    오늘의 당선 메뉴를 계산합니다.

    동점인 경우에는 동점 메뉴 중 가장 최근에 표를 받은 메뉴를
    최종 당선 메뉴로 정합니다.
    """
    if today_votes.empty:
        return None, 0, pd.DataFrame()

    vote_counts = (
        today_votes.groupby("메뉴")
        .size()
        .reset_index(name="득표수")
    )

    max_votes = int(vote_counts["득표수"].max())
    tied_menus = vote_counts[
        vote_counts["득표수"] == max_votes
    ]["메뉴"].tolist()

    if len(tied_menus) == 1:
        winner = tied_menus[0]
    else:
        # 동점 메뉴 가운데 가장 최근 표를 받은 메뉴를 선택합니다.
        winner = (
            today_votes[today_votes["메뉴"].isin(tied_menus)]
            .sort_values("_기록순서")
            .iloc[-1]["메뉴"]
        )

    vote_counts["득표율"] = (
        vote_counts["득표수"] / vote_counts["득표수"].sum() * 100
    ).round(1)

    vote_counts = vote_counts.sort_values(
        ["득표수", "메뉴"],
        ascending=[False, True],
    ).reset_index(drop=True)

    return winner, max_votes, vote_counts


def get_recent_meal_records(df, today):
    """오늘을 포함한 최근 7일간의 '먹었다' 기록을 가져옵니다."""
    if df.empty:
        return empty_dataframe()

    start_date = today - timedelta(days=6)

    recent_meals = df[
        (df["구분"] == "먹었다")
        & (df["날짜"].notna())
        & (df["날짜"] >= start_date)
        & (df["날짜"] <= today)
        & (df["메뉴"].str.strip() != "")
    ].copy()

    return recent_meals.sort_values(
        ["날짜시간", "_기록순서"],
        ascending=[False, False],
    )


def get_days_since_menu_was_eaten(df, winner, today):
    """
    당선 메뉴가 최근 7일 안에 먹은 메뉴인지 확인합니다.

    오늘 먹었다고 기록한 것은 0일 전,
    어제 먹었다면 1일 전으로 표시됩니다.
    """
    if df.empty or not winner:
        return None

    start_date = today - timedelta(days=6)

    same_menu_records = df[
        (df["구분"] == "먹었다")
        & (df["메뉴"] == winner)
        & (df["날짜"].notna())
        & (df["날짜"] >= start_date)
        & (df["날짜"] <= today)
    ].copy()

    if same_menu_records.empty:
        return None

    latest_date = same_menu_records["날짜"].max()
    return (today - latest_date).days


# =========================================================
# 데이터 불러오기
# =========================================================
SHEET_URL = get_sheet_url()

now_kst = datetime.now(KST)
today_kst = now_kst.date()

try:
    records = load_records(SHEET_URL)
except requests.exceptions.Timeout:
    st.error("구글 시트 응답이 늦어지고 있습니다. 잠시 후 다시 시도해주세요.")
    st.stop()
except requests.exceptions.RequestException as error:
    st.error("구글 시트 기록을 불러오지 못했습니다.")
    st.caption(f"오류 내용: {error}")
    st.stop()
except ValueError:
    st.error("구글 시트에서 받은 내용을 JSON으로 읽지 못했습니다.")
    st.caption("Apps Script가 표를 JSON 형식으로 반환하는지 확인해주세요.")
    st.stop()


# =========================================================
# 화면 상단
# =========================================================
st.markdown(
    '<div class="main-title">🍽️ 민주적 점심</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-title">오늘 점심도 평화롭고 민주적으로 정해봅시다.</div>',
    unsafe_allow_html=True,
)

st.caption(
    f"한국 시간 기준 · {now_kst.strftime('%Y년 %m월 %d일 %H:%M')}"
)


# =========================================================
# 투표 입력 영역
# =========================================================
st.subheader("🙋 오늘 뭐 먹을까요?")

member = st.text_input(
    "이름",
    placeholder="이름이나 별명을 입력해주세요.",
    max_chars=30,
)

menu = st.selectbox(
    "먹고 싶은 메뉴",
    MENU_OPTIONS,
)

if st.button(
    "🗳️ 이 메뉴에 한 표",
    type="primary",
    use_container_width=True,
):
    cleaned_member = member.strip()
    cleaned_menu = menu.strip()

    if not cleaned_member:
        st.warning("누구의 소중한 한 표인지 이름을 먼저 알려주세요.")
    else:
        try:
            with st.spinner("소중한 한 표를 투표함에 넣는 중입니다..."):
                save_record(
                    SHEET_URL,
                    member=cleaned_member,
                    menu=cleaned_menu,
                    record_type="먹고싶다",
                )

            # 새 기록을 바로 읽을 수 있도록 기존 캐시를 비웁니다.
            st.cache_data.clear()

            st.success(
                f"'{cleaned_member}'님의 '{cleaned_menu}' 한 표가 접수되었습니다!"
            )
            st.rerun()

        except requests.exceptions.Timeout:
            st.error("투표 접수가 늦어지고 있습니다. 잠시 후 다시 눌러주세요.")
        except requests.exceptions.RequestException as error:
            st.error("투표를 저장하지 못했습니다.")
            st.caption(f"오류 내용: {error}")


st.divider()


# =========================================================
# 기록이 하나도 없는 경우
# =========================================================
if records.empty:
    st.info(
        "아직 쌓인 기록이 없습니다. 첫 번째 메뉴 후보를 올려주세요! "
        "점심 민주주의의 역사가 지금 시작됩니다."
    )
    st.stop()


# =========================================================
# 오늘의 투표 및 당선 메뉴
# =========================================================
today_votes = get_today_votes(records, today_kst)
winner, winner_votes, vote_status = calculate_winner(today_votes)

st.subheader("🏆 오늘의 점심 개표 결과")

if today_votes.empty:
    st.info(
        "오늘 접수된 표가 아직 없습니다. "
        "배고픈 사람이 먼저 용기 있게 한 표를 던져주세요."
    )

else:
    total_voters = len(today_votes)

    st.markdown(
        f"""
        <div class="winner-box">
            <div class="winner-label">오늘의 당선 메뉴</div>
            <div class="winner-menu">{winner}</div>
            <div class="winner-votes">
                {winner_votes}표 획득 · 총 {total_voters}명 참여
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    days_since_eaten = get_days_since_menu_was_eaten(
        records,
        winner,
        today_kst,
    )

    if days_since_eaten is not None:
        if days_since_eaten == 0:
            witty_message = (
                f"그 메뉴, 오늘도 이미 드셨다고 기록되어 있는데 "
                f"또 드셔도 괜찮으시겠어요? 진정한 사랑은 말리지 않겠습니다."
            )
        else:
            witty_message = (
                f"그 메뉴, {days_since_eaten}일 전에도 드셨는데 "
                f"괜찮으시겠어요? 입맛은 제자리로 돌아오는 법이긴 합니다."
            )

        st.markdown(
            f'<div class="warm-message">😏 {witty_message}</div>',
            unsafe_allow_html=True,
        )

    if st.button(
        f"✅ 오늘 {winner} 먹었다",
        use_container_width=True,
    ):
        # 식사 기록을 남기는 사람은 이름 입력값을 사용합니다.
        # 이름이 비어 있다면 '팀'이라는 이름으로 저장합니다.
        meal_member = member.strip() if member.strip() else "팀"

        try:
            with st.spinner("오늘의 점심 역사를 기록하는 중입니다..."):
                save_record(
                    SHEET_URL,
                    member=meal_member,
                    menu=winner,
                    record_type="먹었다",
                )

            st.cache_data.clear()

            st.success(
                f"오늘 '{winner}'을 먹은 것으로 기록했습니다. 맛있게 드세요!"
            )
            st.rerun()

        except requests.exceptions.Timeout:
            st.error("식사 기록 저장이 늦어지고 있습니다. 다시 시도해주세요.")
        except requests.exceptions.RequestException as error:
            st.error("먹은 기록을 저장하지 못했습니다.")
            st.caption(f"오류 내용: {error}")


# =========================================================
# 오늘의 득표 현황
# =========================================================
st.divider()
st.subheader("📊 오늘의 득표 현황")

if today_votes.empty:
    st.caption("오늘의 득표 현황이 아직 비어 있습니다.")
else:
    display_vote_status = vote_status.copy()
    display_vote_status["득표율"] = (
        display_vote_status["득표율"].map(lambda value: f"{value:.1f}%")
    )

    st.dataframe(
        display_vote_status,
        use_container_width=True,
        hide_index=True,
        column_config={
            "메뉴": st.column_config.TextColumn("메뉴"),
            "득표수": st.column_config.NumberColumn(
                "득표수",
                format="%d표",
            ),
            "득표율": st.column_config.TextColumn("득표율"),
        },
    )

    with st.expander("오늘 팀원별 최종 투표 보기"):
        member_vote_table = today_votes[
            ["팀원", "메뉴", "시각"]
        ].copy()

        member_vote_table = member_vote_table.rename(
            columns={
                "팀원": "팀원",
                "메뉴": "최종 선택",
                "시각": "투표 시각",
            }
        )

        st.dataframe(
            member_vote_table,
            use_container_width=True,
            hide_index=True,
        )


# =========================================================
# 최근 7일 동안 먹은 기록
# =========================================================
st.divider()
st.subheader("🗓️ 최근 7일 동안 먹은 기록")

recent_meals = get_recent_meal_records(records, today_kst)

if recent_meals.empty:
    st.info(
        "최근 7일 동안 먹었다고 남긴 기록이 없습니다. "
        "오늘부터 점심 발자취를 차곡차곡 남겨보세요."
    )
else:
    recent_meal_table = recent_meals[
        ["날짜", "메뉴", "팀원", "시각"]
    ].copy()

    recent_meal_table["날짜"] = recent_meal_table["날짜"].apply(
        lambda value: value.strftime("%Y-%m-%d")
        if pd.notna(value)
        else ""
    )

    recent_meal_table = recent_meal_table.rename(
        columns={
            "날짜": "먹은 날짜",
            "메뉴": "먹은 메뉴",
            "팀원": "기록한 사람",
            "시각": "기록 시각",
        }
    )

    st.dataframe(
        recent_meal_table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# 화면 하단
# =========================================================
st.divider()
st.caption(
    "한 사람의 여러 표보다 한 사람의 마지막 선택을 존중합니다. "
    "오늘도 맛있는 합의에 도달하시길 바랍니다. 🍚"
)

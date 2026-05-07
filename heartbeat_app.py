import time
import random
import math
from datetime import datetime
from collections import deque
import streamlit as st
import pandas as pd
import pydeck as pdk

# ==================== 坐标系转换工具 ====================
PI = math.pi
A = 6378245.0
EE = 0.00669342162296594323

def _transform_lat(x, y):
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 320 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret

def _transform_lon(x, y):
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret

def wgs84_to_gcj02(lon, lat):
    if out_of_china(lon, lat):
        return lon, lat
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrtmagic) * PI)
    dlon = (dlon * 180.0) / (A / sqrtmagic * math.cos(radlat) * PI)
    return lon + dlon, lat + dlat

def gcj02_to_wgs84(lon, lat):
    if out_of_china(lon, lat):
        return lon, lat
    wgs_lon, wgs_lat = lon, lat
    for _ in range(5):
        temp_lon, temp_lat = wgs84_to_gcj02(wgs_lon, wgs_lat)
        delta_lon = temp_lon - lon
        delta_lat = temp_lat - lat
        if abs(delta_lon) < 1e-7 and abs(delta_lat) < 1e-7:
            break
        wgs_lon -= delta_lon
        wgs_lat -= delta_lat
    return wgs_lon, wgs_lat

def out_of_china(lon, lat):
    return not (72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271)

# ==================== 页面配置 ====================
st.set_page_config(page_title="无人机导航与监控", layout="wide")

# -------------------- 侧边栏 --------------------
with st.sidebar:
    st.title("功能页面")
    page = st.radio("导航", ["航线规划", "飞行监控"], key="page_select")
    st.markdown("---")
    st.subheader("坐标系设置")
    coord_system = st.radio(
        "输入坐标系",
        ["WGS-84", "GCJ-02 (高德/百度)"],
        index=1,  # 默认 GCJ-02
        key="coord_system"
    )

# ==================== 默认坐标（南京科技职业学院内，GCJ-02） ====================
# A点：学生公寓1幢南侧树林
DEFAULT_A_LAT = 32.2315
DEFAULT_A_LON = 118.7480
# B点：7、8号教学楼之间
DEFAULT_B_LAT = 32.2345
DEFAULT_B_LON = 118.7500

# ==================== 航线规划页面 ====================
if page == "航线规划":
    st.title("🗺️ 航线规划（卫星地图）")
    st.markdown("设置起点 A 和终点 B，点击按钮后在地图上显示。")

    # 初始化存储变量（初始为空，地图空白）
    if "saved_a_lat" not in st.session_state:
        st.session_state.saved_a_lat = None
        st.session_state.saved_a_lon = None
        st.session_state.saved_b_lat = None
        st.session_state.saved_b_lon = None

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🟢 起点 A")
        # 如果已设置过，则显示上次设置的值；否则显示建议值
        a_lat_val = st.session_state.saved_a_lat if st.session_state.saved_a_lat is not None else DEFAULT_A_LAT
        a_lon_val = st.session_state.saved_a_lon if st.session_state.saved_a_lon is not None else DEFAULT_A_LON
        a_lat_input = st.number_input("纬度", value=a_lat_val, format="%.6f", key="a_lat")
        a_lon_input = st.number_input("经度", value=a_lon_val, format="%.6f", key="a_lon")
        if st.button("设置A点"):
            if -90 <= a_lat_input <= 90 and -180 <= a_lon_input <= 180:
                st.session_state.saved_a_lat = a_lat_input
                st.session_state.saved_a_lon = a_lon_input
                st.success(f"A点已设置 ({a_lat_input:.6f}, {a_lon_input:.6f}) [{coord_system}]")
            else:
                st.error("经纬度超出有效范围！")

    with col2:
        st.markdown("### 🔴 终点 B")
        b_lat_val = st.session_state.saved_b_lat if st.session_state.saved_b_lat is not None else DEFAULT_B_LAT
        b_lon_val = st.session_state.saved_b_lon if st.session_state.saved_b_lon is not None else DEFAULT_B_LON
        b_lat_input = st.number_input("纬度", value=b_lat_val, format="%.6f", key="b_lat")
        b_lon_input = st.number_input("经度", value=b_lon_val, format="%.6f", key="b_lon")
        if st.button("设置B点"):
            if -90 <= b_lat_input <= 90 and -180 <= b_lon_input <= 180:
                st.session_state.saved_b_lat = b_lat_input
                st.session_state.saved_b_lon = b_lon_input
                st.success(f"B点已设置 ({b_lat_input:.6f}, {b_lon_input:.6f}) [{coord_system}]")
            else:
                st.error("经纬度超出有效范围！")

    flight_height = st.number_input("设定飞行高度 (m)", value=50, min_value=10, max_value=200, step=5)

    # -------------------- 构建地图图层 --------------------
    layers = []

    # 1. ESRI 卫星底图（WGS-84 坐标系，全球可用）
    esri_satellite = pdk.Layer(
        "TileLayer",
        data="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    )
    layers.append(esri_satellite)

    # 坐标转换辅助函数：输入坐标 → WGS-84
    def to_wgs84(lon, lat, sys):
        if lon is None or lat is None:
            return None, None
        if sys == "GCJ-02 (高德/百度)":
            return gcj02_to_wgs84(lon, lat)
        else:
            return lon, lat

    a_lon_wgs, a_lat_wgs = None, None
    b_lon_wgs, b_lat_wgs = None, None

    if st.session_state.saved_a_lat is not None:
        a_lon_wgs, a_lat_wgs = to_wgs84(st.session_state.saved_a_lon, st.session_state.saved_a_lat, coord_system)
        a_layer = pdk.Layer(
            "ScatterplotLayer",
            data=pd.DataFrame([{"lat": a_lat_wgs, "lon": a_lon_wgs}]),
            get_position=["lon", "lat"],
            get_radius=8,
            get_color=[0, 255, 0, 220],
            pickable=True,
        )
        layers.append(a_layer)

    if st.session_state.saved_b_lat is not None:
        b_lon_wgs, b_lat_wgs = to_wgs84(st.session_state.saved_b_lon, st.session_state.saved_b_lat, coord_system)
        b_layer = pdk.Layer(
            "ScatterplotLayer",
            data=pd.DataFrame([{"lat": b_lat_wgs, "lon": b_lon_wgs}]),
            get_position=["lon", "lat"],
            get_radius=8,
            get_color=[255, 0, 0, 220],
            pickable=True,
        )
        layers.append(b_layer)

    # 如果 A、B 都已设置，绘制航线
    if a_lat_wgs is not None and b_lat_wgs is not None:
        path_df = pd.DataFrame([
            {"lat": a_lat_wgs, "lon": a_lon_wgs},
            {"lat": b_lat_wgs, "lon": b_lon_wgs},
        ])
        path_layer = pdk.Layer(
            "PathLayer",
            data=pd.DataFrame([{"path": [list(path_df.itertuples(index=False, name=None))]}]),
            get_path="path",
            get_width=3,
            get_color=[0, 200, 255],
            width_scale=1,
            pickable=False,
        )
        layers.append(path_layer)

    # 地图中心点：优先已设的 A 点，其次 B 点，否则校园中心（GCJ-02 转 WGS-84）
    if a_lat_wgs and a_lon_wgs:
        center_lat, center_lon = a_lat_wgs, a_lon_wgs
    elif b_lat_wgs and b_lon_wgs:
        center_lat, center_lon = b_lat_wgs, b_lon_wgs
    else:
        # 南京科技职业学院中心 (GCJ-02 转 WGS-84)
        center_lon, center_lat = gcj02_to_wgs84(118.7490, 32.2325)

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=17,
        pitch=0,
        bearing=0,
    )

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style=None,   # 不使用 Mapbox 默认样式，完全依赖 TileLayer
    )

    st.pydeck_chart(deck)

    st.caption(f"底图：ESRI 卫星影像 | 输入坐标系：{coord_system} | 地图使用 WGS-84 坐标系")
    if st.session_state.saved_a_lat is None and st.session_state.saved_b_lat is None:
        st.info("请点击「设置A点」和「设置B点」以显示点位和航线")
    elif st.session_state.saved_a_lat is None:
        st.info("请点击「设置A点」以显示起点")
    elif st.session_state.saved_b_lat is None:
        st.info("请点击「设置B点」以显示终点")
    else:
        st.success("🟢 起点 A   🔴 终点 B  航线已显示")

# ==================== 飞行监控页面（心跳） ====================
elif page == "飞行监控":
    # -------------------- 初始化心跳相关 session_state --------------------
    if 'records' not in st.session_state:
        st.session_state.records = deque(maxlen=200)
        st.session_state.hb_status = "未开始"
        st.session_state.last_success_time = None
        st.session_state.running = False
        st.session_state.seq = 0
        st.session_state.last_gen_time = None

    st.title("📡 飞行监控 — 心跳包状态")

    # -------------------- 心跳生成逻辑 --------------------
    if st.session_state.running:
        now = datetime.now()
        if (st.session_state.last_gen_time is None or
            (now - st.session_state.last_gen_time).total_seconds() >= 1.0):
            st.session_state.last_gen_time = now
            st.session_state.seq += 1
            send_time = now
            time_str = send_time.strftime("%H:%M:%S")

            if random.random() < 0.9:
                recv_time = send_time
                recv_str = recv_time.strftime("%H:%M:%S")
                status = "成功"
            else:
                recv_time = None
                recv_str = "-"
                status = "丢包"

            record = {
                "序号": st.session_state.seq,
                "发送时间": time_str,
                "完整时间": send_time,
                "接收状态": status,
                "接收时间": recv_str
            }
            st.session_state.records.append(record)
            if recv_time is not None:
                st.session_state.last_success_time = recv_time

        if st.session_state.last_success_time is None:
            st.session_state.hb_status = "连接超时"
        else:
            elapsed = (now - st.session_state.last_success_time).total_seconds()
            st.session_state.hb_status = "连接超时" if elapsed > 3 else "正常"

    # -------------------- 控制按钮 --------------------
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 4])
    with col_btn1:
        if st.button("▶️ 开始模拟", disabled=st.session_state.running):
            st.session_state.running = True
            st.session_state.seq = 0
            st.session_state.records.clear()
            st.session_state.last_success_time = None
            st.session_state.hb_status = "正常"
            st.session_state.last_gen_time = None
            st.rerun()
    with col_btn2:
        if st.button("⏹️ 停止模拟", disabled=not st.session_state.running):
            st.session_state.running = False
            st.session_state.hb_status = "已停止"
            st.rerun()
    with col_btn3:
        if st.session_state.running:
            st.info("🟢 模拟运行中...")
        else:
            st.warning("⚪ 模拟已停止" if st.session_state.hb_status == "已停止" else "⚪ 点击开始按钮启动模拟")

    # -------------------- 状态卡片 --------------------
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    records_list = list(st.session_state.records)
    current_hb = st.session_state.hb_status

    with col1:
        if current_hb == "正常":
            st.success("🔵 连接状态：正常")
        elif current_hb == "连接超时":
            st.error("🔴 连接状态：连接超时")
        elif current_hb == "已停止":
            st.warning("⚪ 连接状态：已停止")
        else:
            st.info("⚪ 连接状态：未开始")
    with col2:
        st.metric("📊 总记录数", len(records_list))
    with col3:
        success_count = sum(1 for r in records_list if r["接收状态"] == "成功")
        st.metric("✅ 成功接收", success_count)
    with col4:
        fail_count = sum(1 for r in records_list if r["接收状态"] == "丢包")
        st.metric("❌ 丢包次数", fail_count)

    # -------------------- 数据表格 --------------------
    st.markdown("---")
    st.subheader("📋 心跳数据列表")
    if records_list:
        df = pd.DataFrame(records_list)
        df_display = df[["序号", "发送时间", "接收状态", "接收时间"]].iloc[::-1]
        st.dataframe(df_display, use_container_width=True, height=300)
    else:
        st.info("💡 暂无心跳记录，请点击「开始模拟」按钮")

    # -------------------- 趋势图 --------------------
    st.markdown("---")
    st.subheader("📈 心跳状态趋势（最近100条）")
    if records_list:
        recent = records_list[-100:]
        chart_data = pd.DataFrame({
            "序号": [r["序号"] for r in recent],
            "状态值": [1 if r["接收状态"] == "成功" else 0 for r in recent],
            "发送时间": [r["发送时间"] for r in recent]
        })
        st.line_chart(chart_data, x="序号", y="状态值", use_container_width=True)
        st.markdown("🟢 **1** = 成功   🔴 **0** = 丢包")
        total = len(recent)
        success = sum(1 for r in recent if r["接收状态"] == "成功")
        fail = total - success
        success_rate = (success / total * 100) if total > 0 else 0
        st.progress(success_rate / 100, text=f"最近 {total} 条成功率：{success_rate:.1f}%")
    else:
        st.info("💡 暂无数据")

    st.markdown("---")
    st.caption("💡 切换到「航线规划」可查看地图")

    # 自动刷新（仅运行中）
    if st.session_state.running:
        time.sleep(1)
        st.rerun()
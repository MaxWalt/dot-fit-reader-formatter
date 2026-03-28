import streamlit as st
import pandas as pd
import tempfile
import os

from fit_to_long_format import read_fit_file

st.set_page_config(page_title="FIT File Reader", page_icon="🏃", layout="wide")

st.title("🏃 FIT File Reader")
st.caption("Upload one or more .fit files to extract section data (time, speed, distance).")

uploaded_files = st.file_uploader(
    "Drop your .fit files here",
    type=["fit"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("Upload a .fit file to get started.")
    st.stop()

all_rows = []
errors = []

for uploaded_file in uploaded_files:
    with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name
    try:
        rows = read_fit_file(tmp_path)
        # Replace the temp filename with the original name
        for row in rows:
            row["source_file"] = uploaded_file.name
        all_rows.extend(rows)
    except Exception as e:
        errors.append(f"**{uploaded_file.name}**: {e}")
    finally:
        os.unlink(tmp_path)

for err in errors:
    st.error(err)

if not all_rows:
    st.stop()

df = pd.DataFrame(all_rows)

# ── Summary cards ──────────────────────────────────────────────────────────────
st.subheader("Summary")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Files", df["source_file"].nunique())
col2.metric("Sections", len(df))
col3.metric("Total distance", f"{df['distance_km'].sum():.2f} km")
col4.metric("Total time", f"{df['time_s'].sum() / 60:.1f} min")

st.divider()

# ── Charts ─────────────────────────────────────────────────────────────────────
st.subheader("Charts")
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("**Avg speed per section (km/h)**")
    chart_data = df[["section", "avg_speed_km_h", "source_file"]].copy()
    st.bar_chart(chart_data.set_index("section")["avg_speed_km_h"])

with chart_col2:
    st.markdown("**Distance per section (km)**")
    st.bar_chart(df.set_index("section")["distance_km"])

st.divider()

# ── Data table ─────────────────────────────────────────────────────────────────
st.subheader("Section data")

# Optional file filter when multiple files are loaded
if df["source_file"].nunique() > 1:
    selected_files = st.multiselect(
        "Filter by file",
        options=df["source_file"].unique().tolist(),
        default=df["source_file"].unique().tolist(),
    )
    df_view = df[df["source_file"].isin(selected_files)]
else:
    df_view = df

st.dataframe(
    df_view,
    use_container_width=True,
    hide_index=True,
    column_config={
        "time_s":          st.column_config.NumberColumn("Time (s)",      format="%.1f"),
        "avg_speed_m_s":   st.column_config.NumberColumn("Speed (m/s)",   format="%.3f"),
        "avg_speed_km_h":  st.column_config.NumberColumn("Speed (km/h)",  format="%.2f"),
        "distance_m":      st.column_config.NumberColumn("Distance (m)",  format="%.1f"),
        "distance_km":     st.column_config.NumberColumn("Distance (km)", format="%.3f"),
    },
)

# ── CSV download ───────────────────────────────────────────────────────────────
csv = df_view.to_csv(index=False).encode("utf-8")
st.download_button(
    label="⬇ Download CSV",
    data=csv,
    file_name="sections_long_format.csv",
    mime="text/csv",
)

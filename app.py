import streamlit as st
import pandas as pd
import tempfile
import os

from fit_to_long_format import read_fit_file

st.set_page_config(page_title="FIT File Reader", page_icon="🏃", layout="wide")

st.title("🏃 FIT File Reader")
st.caption("Upload one or more .fit files to extract per-section metrics.")

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

# Warn if any distances were derived rather than read from file
n_derived = df["distance_derived"].sum() if "distance_derived" in df.columns else 0
if n_derived > 0:
    st.warning(
        f"{int(n_derived)} section(s) had no distance in the file — "
        "distance was calculated from avg speed × time."
    )

# ── Aerobic decoupling (Pa:Hr) ─────────────────────────────────────────────────
# Computed per file from efficiency_factor (speed/HR).
# Split sections into two halves; decoupling = drop in efficiency 1st→2nd half.
# < 5 % = well-coupled (aerobically fit for that effort).
def compute_decoupling(group: pd.DataFrame) -> float | None:
    """Duration-weighted Pa:Hr decoupling, split at the 50 % time mark."""
    g = group[["efficiency_factor", "time_s"]].dropna()
    if len(g) < 2:
        return None
    total_time = g["time_s"].sum()
    cumulative = g["time_s"].cumsum()
    first  = g[cumulative <= total_time / 2]
    second = g[cumulative >  total_time / 2]
    if first.empty or second.empty:
        return None
    ef1 = (first["efficiency_factor"]  * first["time_s"]).sum()  / first["time_s"].sum()
    ef2 = (second["efficiency_factor"] * second["time_s"]).sum() / second["time_s"].sum()
    if ef1 == 0:
        return None
    return round((ef1 - ef2) / ef1 * 100, 2)

# ── Summary cards ──────────────────────────────────────────────────────────────
st.subheader("Summary")
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Files",          df["source_file"].nunique())
c2.metric("Sections",       len(df))
c3.metric("Total distance", f"{df['distance_km'].sum():.2f} km")
c4.metric("Total time",     f"{df['time_s'].sum() / 60:.1f} min")
if df["calories_kcal"].notna().any():
    c5.metric("Total calories", f"{int(df['calories_kcal'].sum())} kcal")
if df["total_ascent_m"].notna().any():
    c6.metric("Total ascent", f"{int(df['total_ascent_m'].sum())} m")

# Aerobic decoupling per file
if df["efficiency_factor"].notna().any():
    st.subheader("Aerobic decoupling (Pa:Hr)")
    st.caption(
        "Compares efficiency (speed ÷ HR) between the first and second half of each session. "
        "< 5 % = well-coupled | > 5 % = cardiac drift detected."
    )
    dec_cols = st.columns(min(len(uploaded_files), 4))
    for idx, fname in enumerate(df["source_file"].unique()):
        dec = compute_decoupling(df[df["source_file"] == fname])
        if dec is not None:
            label = "✅ Well-coupled" if dec < 5 else "⚠️ Drift detected"
            dec_cols[idx % len(dec_cols)].metric(
                fname, f"{dec:.1f} %", label
            )

st.divider()

# ── File filter ────────────────────────────────────────────────────────────────
if df["source_file"].nunique() > 1:
    selected_files = st.multiselect(
        "Filter by file",
        options=df["source_file"].unique().tolist(),
        default=df["source_file"].unique().tolist(),
    )
    df = df[df["source_file"].isin(selected_files)]

# ── Charts ─────────────────────────────────────────────────────────────────────
def has_data(col):
    return col in df.columns and df[col].notna().any()

st.subheader("Charts")

# Row 1 — Speed & Distance
col1, col2 = st.columns(2)
with col1:
    st.markdown("**Avg speed per section (km/h)**")
    st.bar_chart(df.set_index("section")["avg_speed_km_h"])
with col2:
    st.markdown("**Distance per section (km)**")
    st.bar_chart(df.set_index("section")["distance_km"])

# Row 2 — HR & HR drift
if has_data("avg_hr_bpm"):
    col3, col4 = st.columns(2)
    with col3:
        st.markdown("**Avg HR per section (bpm)**")
        st.bar_chart(df.set_index("section")["avg_hr_bpm"])
    with col4:
        st.markdown("**HR drift across sections (Δ bpm from previous)**")
        hr_drift = df.set_index("section")["avg_hr_bpm"].diff()
        st.bar_chart(hr_drift)

# Row 3 — Efficiency factor & Cadence
if has_data("efficiency_factor") or has_data("avg_cadence_rpm"):
    col5, col6 = st.columns(2)
    with col5:
        if has_data("efficiency_factor"):
            st.markdown("**Efficiency factor per section (km/h per bpm)**")
            st.line_chart(df.set_index("section")["efficiency_factor"])
    with col6:
        if has_data("avg_cadence_rpm"):
            st.markdown("**Avg cadence per section**")
            st.bar_chart(df.set_index("section")["avg_cadence_rpm"])

# Row 4 — Stride length
if has_data("avg_stride_length_m"):
    col_sl, _ = st.columns(2)
    with col_sl:
        st.markdown("**Avg stride length per section (m)**")
        st.bar_chart(df.set_index("section")["avg_stride_length_m"])

# Row 5 — Power & Altitude
if has_data("avg_power_w") or has_data("avg_altitude_m"):
    col7, col8 = st.columns(2)
    with col7:
        if has_data("avg_power_w"):
            st.markdown("**Avg power per section (W)**")
            st.bar_chart(df.set_index("section")["avg_power_w"])
    with col8:
        if has_data("avg_altitude_m"):
            st.markdown("**Avg altitude per section (m)**")
            st.bar_chart(df.set_index("section")["avg_altitude_m"])

st.divider()

# ── Data table ─────────────────────────────────────────────────────────────────
st.subheader("Section data")

df_view = df.dropna(axis=1, how="all")
df_view = df_view.drop(columns=["distance_derived", "step_length_derived"], errors="ignore")

column_config = {
    "workout_name":            st.column_config.TextColumn("Workout name"),
    "time_s":                  st.column_config.NumberColumn("Time (s)",          format="%.1f"),
    "elapsed_time_s":          st.column_config.NumberColumn("Elapsed (s)",       format="%.1f"),
    "avg_speed_m_s":           st.column_config.NumberColumn("Avg spd (m/s)",     format="%.3f"),
    "avg_speed_km_h":          st.column_config.NumberColumn("Avg spd (km/h)",    format="%.2f"),
    "distance_m":              st.column_config.NumberColumn("Distance (m)",      format="%.1f"),
    "distance_km":             st.column_config.NumberColumn("Distance (km)",     format="%.3f"),
    "avg_hr_bpm":              st.column_config.NumberColumn("Avg HR (bpm)",          format="%d"),
    "hr_drift_bpm":            st.column_config.NumberColumn("HR drift (Δ bpm)",      format="%.1f"),
    "avg_cadence_rpm":         st.column_config.NumberColumn("Avg cadence",           format="%d"),
    "avg_step_length_m":       st.column_config.NumberColumn("Step length (m)",       format="%.3f"),
    "avg_stride_length_m":     st.column_config.NumberColumn("Stride length (m)",     format="%.3f"),
    "efficiency_factor":       st.column_config.NumberColumn("Efficiency (km/h/bpm)", format="%.4f"),
    "aerobic_decoupling_pct":  st.column_config.NumberColumn("Aerobic decoupling (%)", format="%.2f"),
    "avg_power_w":             st.column_config.NumberColumn("Avg power (W)",     format="%d"),
    "normalized_power_w":      st.column_config.NumberColumn("NP (W)",            format="%d"),
    "avg_altitude_m":          st.column_config.NumberColumn("Avg alt (m)",       format="%.1f"),
    "total_ascent_m":          st.column_config.NumberColumn("Ascent (m)",        format="%d"),
    "total_descent_m":         st.column_config.NumberColumn("Descent (m)",       format="%d"),
    "avg_grade_pct":           st.column_config.NumberColumn("Avg grade (%)",     format="%.1f"),
    "calories_kcal":           st.column_config.NumberColumn("Calories (kcal)",   format="%d"),
    "avg_temperature_c":       st.column_config.NumberColumn("Temp (°C)",         format="%.1f"),
}

st.dataframe(df_view, use_container_width=True, hide_index=True, column_config=column_config)

# ── CSV download ───────────────────────────────────────────────────────────────
csv_bytes = df_view.to_csv(index=False).encode("utf-8")
st.download_button(
    label="⬇ Download CSV",
    data=csv_bytes,
    file_name="sections_long_format.csv",
    mime="text/csv",
)

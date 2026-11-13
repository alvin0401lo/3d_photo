"""Small native Streamlit host for the existing interactive editor."""
import streamlit as st

st.set_page_config(page_title="DepthFrame AI", page_icon=":material/view_in_ar:", layout="wide", initial_sidebar_state="collapsed")
st.title("DepthFrame AI")
st.caption("Private hosted workspace · photo depth, environment panoramas, and selected-object 360°")
with st.container(horizontal=True):
    st.link_button("Open full editor", "workspace/", icon=":material/open_in_new:")
    st.caption("Keep this deployment private. Photos are stored on the app server; download your results before a restart.")
# Resolve in the browser: Community Cloud's /~/+/ proxy prefix is absent server-side.
# st.iframe treats a non-slash relative URL as HTML, so use a trusted bootstrap.
st.iframe('''<!doctype html><html><head><meta charset="utf-8"></head><body>
<script>window.location.replace(new URL("workspace/", document.baseURI).href);</script>
<noscript>Enable JavaScript to open the photo editor.</noscript>
</body></html>''', height=1050, alt="DepthFrame photo editor with environment and object 360 degree viewers")
with st.expander("Hosting and API configuration"):
    st.markdown("Add `MESHY_API_KEY` and/or `OPENAI_API_KEY` in **Streamlit app settings → Secrets**. Never put real keys in GitHub. Generation sends only the selected input after consent and uses the configured API account's credits.")
    st.markdown("The CPU depth model downloads on the first start. If depth is unavailable, allow setup to finish and inspect the Community Cloud logs. Captured panorama and 3D sample viewing work without API keys.")
    st.markdown("This remains a single-user app. Use **private app access** in Community Cloud. Its server disk is temporary and is not a durable backup.")

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.interpolate import PchipInterpolator
import io
from google.oauth2 import service_account
from google.cloud import firestore
import base64

# ======================
# פונקציות עזר
# ======================

def deep_clean_value(value):
    """ניקוי עמוק של ערכים לאחסון ב-session_state (רקורסיבי)"""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    elif isinstance(value, pd.DataFrame):
        return value.to_dict(orient='split')
    elif isinstance(value, pd.Series):
        return value.to_dict()
    elif isinstance(value, pd.Timestamp):
        return value.isoformat()
    elif isinstance(value, np.ndarray):
        return value.tolist()
    elif isinstance(value, bytes):
        return base64.b64encode(value).decode('utf-8')
    elif isinstance(value, list):
        return [deep_clean_value(v) for v in value]
    elif isinstance(value, dict):
        return {k: deep_clean_value(v) for k, v in value.items()}
    else:
        return str(value)

def safe_set_session_state_from_loaded_data(loaded_data):
    """עדכון session_state עם ערכים מנוקים"""
    for key, value in loaded_data.items():
        cleaned_value = deep_clean_value(value)
        st.session_state[key] = cleaned_value

def delete_scenario(user_id, scenario_name):
    """מחיקת תרחיש מ-Firestore"""
    if not db or not user_id or not scenario_name:
        st.sidebar.warning("User ID and Scenario Name are required to delete.")
        return
    try:
        db.collection('users').document(user_id).collection('scenarios').document(scenario_name).delete()
        st.sidebar.success(f"Scenario '{scenario_name}' deleted!")
    except Exception as e:
        st.sidebar.error(f"Error deleting scenario: {e}")

# ======================
# הגדרות עמוד
# ======================
st.set_page_config(layout="wide", page_title="Advanced Business Plan Dashboard")
sns.set_theme(style="darkgrid", font_scale=1.1, palette="viridis")

if 'products' not in st.session_state:
    st.session_state.products = ["Product A", "Product B"]
if 'results' not in st.session_state:
    st.session_state.results = {}

# ======================
# חיבור לבסיס הנתונים
# ======================
@st.cache_resource
def init_connection():
    try:
        creds_json = dict(st.secrets.firebase)
        creds = service_account.Credentials.from_service_account_info(creds_json)
        return firestore.Client(credentials=creds, project=creds_json['project_id'])
    except Exception as e:
        st.error(f"Failed to connect to Firebase. Error: {e}")
        return None

db = init_connection()

# ======================
# פונקציות שמירה/טעינה
# ======================
def save_scenario(user_id, scenario_name, data):
    if not db or not user_id or not scenario_name:
        return
    try:
        data_to_save = {k: v for k, v in data.items() if isinstance(k, str) and not k.startswith(('FormSubmitter', 'results', '_'))}
        db.collection('users').document(user_id).collection('scenarios').document(scenario_name).set(data_to_save)
        st.sidebar.success(f"Scenario '{scenario_name}' saved!")
    except Exception as e:
        st.sidebar.error(f"Error saving scenario: {e}")

def get_user_scenarios(user_id):
    if not db or not user_id:
        return []
    try:
        docs = db.collection('users').document(user_id).collection('scenarios').stream()
        return [""] + [doc.id for doc in docs]
    except:
        return [""]

def load_scenario_data(user_id, scenario_name):
    if not db or not user_id or not scenario_name:
        return None
    try:
        doc_ref = db.collection('users').document(user_id).collection('scenarios').document(scenario_name)
        doc = doc_ref.get()
        if doc.exists:
            st.sidebar.info(f"Loaded '{scenario_name}'.")
            return doc.to_dict()
        else:
            st.sidebar.warning("Scenario not found.")
            return None
    except Exception as e:
        st.sidebar.error(f"Error loading: {e}")
        return None

# ======================
# פונקציות חישוב
# ======================
def calculate_plan(is_m, is_l, is_g, market_gr, pen_y1, tt_m, tt_l, tt_g,
                   annual_rev_targets, f_m, f_l, f_g, ip_kg, pdr, price_floor):
    START_YEAR = 2025
    NUM_YEARS = 6
    years = np.array([START_YEAR + i for i in range(NUM_YEARS)])
    quarters_index = pd.date_range(start=f'{START_YEAR}-01-01', periods=NUM_YEARS * 4, freq='QE')
    customer_types = ['Medium', 'Large', 'Global']

    tons_per_customer = pd.DataFrame(index=years, columns=customer_types, dtype=float)
    tons_per_customer.loc[START_YEAR] = [is_m, is_l, is_g]

    initial_tons = {'Medium': is_m, 'Large': is_l, 'Global': is_g}
    target_tons = {'Medium': tt_m, 'Large': tt_l, 'Global': tt_g}
    pen_rate_df = pd.DataFrame(index=range(1, NUM_YEARS + 1), columns=customer_types)

    for c_type in customer_types:
        total_market_growth_factor = (1 + market_gr / 100) ** (NUM_YEARS - 1)
        required_pen_growth_factor = (target_tons[c_type] / initial_tons[c_type]) / total_market_growth_factor if initial_tons[c_type] else 1.0
        pen_rate_y_final = (pen_y1 / 100) * required_pen_growth_factor
        interp_func = PchipInterpolator([1, 2.5, NUM_YEARS],
                                       [pen_y1 / 100, (pen_y1/100 + pen_rate_y_final)/2, pen_rate_y_final])
        pen_rate_df[c_type] = interp_func(range(1, NUM_YEARS + 1))

    for year_idx in range(1, NUM_YEARS):
        prev_year = years[year_idx - 1]
        for c_type in customer_types:
            prev_tons = tons_per_customer.loc[prev_year, c_type]
            tons_per_customer.loc[years[year_idx], c_type] = prev_tons * (1 + market_gr / 100) * (
                        pen_rate_df.loc[year_idx + 1, c_type] / pen_rate_df.loc[year_idx, c_type])

    prices = []
    current_price = ip_kg
    for _ in quarters_index:
        prices.append(current_price)
        current_price = max(current_price * (1 - pdr / 100.0), price_floor)
    price_per_ton_q = pd.Series(prices, index=quarters_index) * 1000
    tons_per_cust_q = tons_per_customer.loc[quarters_index.year].set_axis(quarters_index) / 4

    quarterly_rev_targets = pd.Series(np.repeat(annual_rev_targets, 4) / 4, index=quarters_index)
    total_focus = f_m + f_l + f_g
    focus_norm = {k: v / total_focus for k, v in zip(customer_types, [f_m, f_l, f_g])}

    new_customers = pd.DataFrame(0.0, index=quarters_index, columns=customer_types)
    cumulative_customers = pd.DataFrame(0.0, index=quarters_index, columns=customer_types)

    for i, q_date in enumerate(quarters_index):
        prev_cumulative = cumulative_customers.iloc[i - 1] if i > 0 else pd.Series(0.0, index=customer_types)
        revenue_gap = quarterly_rev_targets.loc[q_date] \
                      - (tons_per_cust_q.loc[q_date] * price_per_ton_q.loc[q_date] * prev_cumulative).sum()
        if revenue_gap > 0:
            blended_rev = (tons_per_cust_q.loc[q_date] * price_per_ton_q.loc[q_date] * pd.Series(focus_norm)).sum()
            if blended_rev > 0:
                total_new_cust = revenue_gap / blended_rev
                for ct in customer_types:
                    new_customers.loc[q_date, ct] = total_new_cust * focus_norm[ct]
        cumulative_customers.loc[q_date] = prev_cumulative + new_customers.loc[q_date]

    return {
        "cumulative_customers": cumulative_customers.round().astype(int),
        "annual_revenue": (tons_per_cust_q.mul(price_per_ton_q, axis=0) *
                           cumulative_customers.round().astype(int)).sum(axis=1).resample('YE').sum().rename(index=lambda x: x.year),
        "annual_revenue_targets": pd.Series(annual_rev_targets, index=years),
        "tons_per_customer": tons_per_customer,
        "pen_rate_df": pen_rate_df,
        "acquired_customers_plan": new_customers.astype(int),
        "error": None
    }

def create_lead_plan(acquired_customers_plan, success_rates, time_aheads_in_quarters):
    quarters_index = acquired_customers_plan.index
    lead_plan = pd.DataFrame(0, index=quarters_index, columns=acquired_customers_plan.columns)
    for q_date, row in acquired_customers_plan.iterrows():
        for c_type in acquired_customers_plan.columns:
            if row[c_type] > 0:
                target_period = q_date.to_period('Q') - time_aheads_in_quarters[c_type]
                idx_matches = lead_plan.index[lead_plan.index.to_period('Q') == target_period]
                if len(idx_matches) > 0:
                    lead_plan.loc[idx_matches[0], c_type] += int(np.ceil(row[c_type] / (success_rates[c_type] / 100.0)))
    return lead_plan.astype(int)

# ======================
# UI
# ======================
st.title("🚀 Dynamic Multi-Product Business Plan Dashboard")

with st.sidebar:
    st.title("Business Plan Controls")
    with st.expander("User & Scenarios", expanded=True):
        user_id = st.text_input("Enter your User ID", key="user_id")
        if user_id and db:
            saved_scenarios = get_user_scenarios(user_id)
            if len(saved_scenarios) > 1:
                st.markdown("#### Saved Scenarios")
                for sname in saved_scenarios[1:]:
                    cols = st.columns([5,1])
                    if cols[0].button(f"Load '{sname}'", key=f"load_{sname}"):
                        loaded_data = load_scenario_data(user_id, sname)
                        if loaded_data:
                            st.session_state.results = {}
                            safe_set_session_state_from_loaded_data(loaded_data)
                            st.rerun()
                    if cols[1].button("❌", key=f"del_{sname}"):
                        delete_scenario(user_id, sname)
                        st.rerun()
            else:
                st.caption("No scenarios found.")

            scenario_name_to_save = st.text_input("Save as scenario name:", key="scenario_name")
            if st.button("Save Current") and scenario_name_to_save:
                all_inputs = {'user_id': user_id, 'products': st.session_state.products}
                for key, value in st.session_state.items():
                    if isinstance(key, str) and key not in ['results', 'user_id', 'products',
                                                            'load_scenario_select', 'scenario_name', 'new_product_name_input']:
                        if not key.startswith('FormSubmitter'):
                            all_inputs[key] = value
                save_scenario(user_id, scenario_name_to_save, all_inputs)

# ... מכאן ממשיכים את חלק ניהול המוצרים, הכנסת פרמטרים, הרצה והצגת התוצאות שלך בדיוק כמו בקוד שלך ...


    with st.expander("Manage Products"):
        for i, product_name in enumerate(st.session_state.get('products', ["Product A", "Product B"])):
            st.session_state.products[i] = st.text_input(f"Product {i+1} Name", value=st.session_state.get(f"pname_{i}", product_name), key=f"pname_{i}")
        
        new_product_name = st.text_input("New Product Name", key="new_product_name_input")
        if st.button("Add Product") and new_product_name:
            if new_product_name not in st.session_state.products:
                st.session_state.products.append(new_product_name)
                st.rerun()
            else:
                st.warning("Product name already exists.")

    with st.expander("Lead Generation Parameters (Global)"):
        lead_params = { 'success_rates': {}, 'time_aheads_in_quarters': {} }
        customer_types_for_leads = ['Medium', 'Large', 'Global']
        sr_defaults = {'Medium': 50, 'Large': 40, 'Global': 30}
        ta_defaults = {'Medium': 3, 'Large': 4, 'Global': 6}
        for c_type in customer_types_for_leads:
            sr_key = f'sr_{c_type}'
            ta_key = f'ta_{c_type}'
            lead_params['success_rates'][c_type] = st.slider(f'Success Rate (%) - {c_type}', 0, 100, st.session_state.get(sr_key, sr_defaults[c_type]), key=sr_key)
            lead_params['time_aheads_in_quarters'][c_type] = st.slider(f'Time Ahead (Quarters) - {c_type}', 1, 12, st.session_state.get(ta_key, ta_defaults[c_type]), key=ta_key)
    
    product_inputs = {}
    for product in st.session_state.products:
        st.header(product)
        product_inputs[product] = {}
        with st.expander(f"1. Initial Customer Value", expanded=False):
            product_inputs[product]['is_m'] = st.number_input('Initial Tons/Customer - Medium:', 0.0, value=st.session_state.get(f'is_m_{product}', 1.5), step=0.1, key=f'is_m_{product}')
            product_inputs[product]['is_l'] = st.number_input('Initial Tons/Customer - Large:', 0.0, value=st.session_state.get(f'is_l_{product}', 10.0), step=1.0, key=f'is_l_{product}')
            product_inputs[product]['is_g'] = st.number_input('Initial Tons/Customer - Global:', 0.0, value=st.session_state.get(f'is_g_{product}', 40.0), step=2.0, key=f'is_g_{product}')
        with st.expander(f"2. Customer Value Growth", expanded=False):
            product_inputs[product]['market_gr'] = st.slider('Annual Market Growth Rate (%):', 0.0, 20.0, st.session_state.get(f'mgr_{product}', 6.4), 0.1, key=f'mgr_{product}')
            product_inputs[product]['pen_y1'] = st.slider('Penetration Rate Year 1 (%):', 1.0, 20.0, st.session_state.get(f'pen_y1_{product}', 7.5), 0.1, key=f'pen_y1_{product}')
            product_inputs[product]['tt_m'] = st.number_input('Target Tons/Cust Year 5 - Medium:', 0.0, value=st.session_state.get(f'tt_m_{product}', 89.0), key=f'tt_m_{product}')
            product_inputs[product]['tt_l'] = st.number_input('Target Tons/Cust Year 5 - Large:', 0.0, value=st.session_state.get(f'tt_l_{product}', 223.0), key=f'tt_l_{product}')
            product_inputs[product]['tt_g'] = st.number_input('Target Tons/Cust Year 5 - Global:', 0.0, value=st.session_state.get(f'tt_g_{product}', 536.0), key=f'tt_g_{product}')
        with st.expander(f"3. Revenue Targets & Sales Strategy", expanded=False):
            st.markdown("**Target Annual Revenue ($)**")
            default_revenues = [300000, 2700000, 5500000, 12000000, 32000000, 40000000]
            rev_targets = []
            for i in range(6):
                year_num = i + 1
                key = f'rev_y{year_num}_{product}'
                rev_slider_val = st.slider(f'Year {year_num}:', 0, 50_000_000, st.session_state.get(key, default_revenues[i]), 100000, format="$%d", key=key)
                rev_targets.append(rev_slider_val)
            product_inputs[product]['annual_rev_targets'] = rev_targets
            st.markdown("---")
            st.markdown("**Sales Focus (%)**")
            product_inputs[product]['f_m'] = st.slider('Medium:', 0, 100, st.session_state.get(f'f_m_{product}', 50), 5, key=f'f_m_{product}')
            product_inputs[product]['f_l'] = st.slider('Large:', 0, 100, st.session_state.get(f'f_l_{product}', 30), 5, key=f'f_l_{product}')
            product_inputs[product]['f_g'] = st.slider('Global:', 0, 100, st.session_state.get(f'f_g_{product}', 20), 5, key=f'f_g_{product}')
        with st.expander(f"4. Pricing Assumptions", expanded=False):
            product_inputs[product]['ip_kg'] = st.number_input('Initial Price per Kg ($):', 0.0, value=st.session_state.get(f'ip_kg_{product}', 18.0), step=0.5, key=f'ip_kg_{product}')
            product_inputs[product]['pdr'] = st.slider('Quarterly Price Decay (%):', 0.0, 10.0, st.session_state.get(f'pdr_{product}', 3.65), 0.05, key=f'pdr_{product}')
            product_inputs[product]['price_floor'] = st.number_input('Minimum Price ($):', 0.0, value=st.session_state.get(f'price_floor_{product}', 14.0), step=0.5, key=f'price_floor_{product}')
    
    run_button = st.sidebar.button("Run Full Analysis", use_container_width=True)

# --- App Logic and Display ---
if run_button:
    results_data = {}
    for product in st.session_state.products:
        res = calculate_plan(**product_inputs[product])
        if res.get("error"):
            st.error(f"Error for {product}: {res['error']}"); st.stop()
        
        final_cumulative = res["cumulative_customers"].round().astype(int)
        acquired_customers = final_cumulative.diff(axis=0).fillna(final_cumulative.iloc[0]).clip(lower=0).astype(int)
        
        res['acquired_customers_plan'] = acquired_customers
        res['cumulative_customers'] = final_cumulative
        res['lead_plan'] = create_lead_plan(acquired_customers, **lead_params)
        results_data[product] = res
    st.session_state.results = results_data

if st.session_state.results:
    results = st.session_state.results
    tabs = st.tabs([*st.session_state.products, "Overall Summary"])
    
    for i, product_name in enumerate(st.session_state.products):
        with tabs[i]:
            st.header(f"Results for {product_name}")
            
            lead_plan_display = results[product_name]["lead_plan"].T
            lead_plan_display.columns = [f"{c.year}-Q{c.quarter}" for c in lead_plan_display.columns]

            acquired_customers_display = results[product_name]["acquired_customers_plan"].T
            acquired_customers_display.columns = [f"{c.year}-Q{c.quarter}" for c in acquired_customers_display.columns]
            
            cum_cust_display = results[product_name]["cumulative_customers"].T
            cum_cust_display.columns = [f"{c.year}-Q{c.quarter}" for c in cum_cust_display.columns]

            validation_df = pd.DataFrame({
                'Target Revenue': results[product_name]['annual_revenue_targets'],
                'Actual Revenue': results[product_name]['annual_revenue']
            })
            validation_df.index.name = "Year"
            results[product_name]['validation_df'] = validation_df
            
            st.subheader("Lead Generation")
            st.markdown("#### Table 0: Recommended Lead Contact Plan")
            st.dataframe(lead_plan_display.style.format("{:d}"))

            st.subheader("Action Plan & Outcomes")
            st.markdown("#### Table 1: Acquired New Customers per Quarter")
            st.dataframe(acquired_customers_display.style.format("{:d}"))

            st.markdown("#### Table 2: Cumulative Number of Customers (Quarterly)")
            st.dataframe(cum_cust_display.style.format("{:,d}"))

            st.markdown("#### Table 3: Target vs. Actual Revenue")
            st.dataframe(validation_df.style.format({'Target Revenue': "${:,.0f}", 'Actual Revenue': "${:,.0f}"}))
            
            st.markdown("#### Chart: Target vs. Actual Annual Revenue ($)")
            plot_df = validation_df.reset_index()
            plot_df_melted = plot_df.melt(id_vars='Year', var_name='Type', value_name='Revenue')
            
            fig, ax = plt.subplots(figsize=(14, 7))
            barplot = sns.barplot(data=plot_df_melted, x='Year', y='Revenue', hue='Type', ax=ax, palette="mako")
            
            ax.set_title(f'Target vs. Actual Revenue - {product_name}', fontsize=18, weight='bold')
            ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x/1_000_000:.1f}M"))
            ax.set_xlabel("Year", fontsize=12)
            ax.set_ylabel("Revenue", fontsize=12)
            # הוספת הטבלאות החסרות
            with st.expander("View Underlying Assumptions"):
                # שליפת הדאטה פריימים מהתוצאות
                tons_per_customer_df = results[product_name].get('tons_per_customer')
                pen_rate_df = results[product_name].get('pen_rate_df')
                
                if tons_per_customer_df is not None:
                    st.markdown("#### Table 4: Annual Tons per Single Customer (Target-Driven)")
                    st.dataframe(tons_per_customer_df.T.style.format("{:,.2f}"))
                
                if pen_rate_df is not None:
                    st.markdown("#### Table 5: Generated Penetration Rates to Meet Target (%)")
                    st.dataframe((pen_rate_df.T*100).style.format("{:,.1f}%"))
            for container in barplot.containers:
                ax.bar_label(container, fmt='${:,.0f}', padding=5, fontsize=9, rotation=45)
            st.pyplot(fig)

    with tabs[-1]:
        st.header("Overall Summary (All Products)")
        
        summary_revenue_list = [results[p]['annual_revenue'] for p in st.session_state.products]
        summary_revenue_df = pd.concat(summary_revenue_list, axis=1).sum(axis=1).to_frame(name="Total Revenue")
        
        summary_customers_list = [results[p]['cumulative_customers'] for p in st.session_state.products]
        summary_customers_total_q_raw = pd.concat(summary_customers_list, axis=1).sum(axis=1)
        summary_customers_total_q = summary_customers_total_q_raw.round().astype(int)
        
        st.markdown("#### Summary: Total Revenue per Year")
        st.dataframe(summary_revenue_df.style.format("${:,.0f}"))

        summary_customers_display = summary_customers_total_q.to_frame(name="Total Customers").T
        summary_customers_display.columns = [f"{c.year}-Q{c.quarter}" for c in summary_customers_display.columns]
        st.markdown("#### Summary: Total Cumulative Customers (Quarterly)")
        st.dataframe(summary_customers_display.style.format("{:,d}"))

        st.markdown("#### Chart: Total Revenue Breakdown by Product")
        all_revenues = {p: results[p]['annual_revenue'] for p in st.session_state.products}
        summary_plot_df = pd.DataFrame(all_revenues)
        summary_plot_df_melted = summary_plot_df.reset_index().rename(columns={'index': 'Year'}).melt(id_vars='Year', var_name='Product', value_name='Revenue')
        
        fig_sum, ax_sum = plt.subplots(figsize=(15, 8))
        
        summary_barplot = sns.barplot(data=summary_plot_df_melted, x='Year', y='Revenue', hue='Product', ax=ax_sum, palette="rocket_r")

        for container in ax_sum.containers:
            ax_sum.bar_label(
                container,
                fmt='$ {:,.0f}',
                rotation=45,
                padding=8,
                fontsize=10,
                color='black',
                fontweight='bold'
            )

        ax_sum.set_title('Total Revenue Breakdown by Product', fontsize=18, weight='bold')
        ax_sum.set_ylabel('Revenue ($)', fontsize=12)
        ax_sum.set_xlabel('Year', fontsize=12)
        ax_sum.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x/1_000_000:.0f}M"))
        ax_sum.tick_params(axis='x', rotation=0)
        st.pyplot(fig_sum)
    
    excel_results_to_pass = {}
    for prod_name, res_data in results.items():
        excel_results_to_pass[prod_name] = res_data.copy()
    
    summary_for_excel = {
        "summary_revenue": summary_revenue_df,
        "summary_customers_raw": summary_customers_total_q_raw
    }
    
    excel_data = to_excel({**excel_results_to_pass, "summary": summary_for_excel})
    st.download_button(label="📥 Download Full Report to Excel", data=excel_data, file_name="Business_Plan_Full_Report.xlsx")

if not run_button and not st.session_state.results:
    st.info("Set your parameters in the sidebar and click 'Run Full Analysis' to see the results.")

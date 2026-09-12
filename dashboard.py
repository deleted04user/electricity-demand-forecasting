"""
Electricity Demand Forecasting Dashboard
Interactive Streamlit application for model exploration and predictions
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import joblib
from datetime import datetime, timedelta
import warnings
from holidays import country_holidays
warnings.filterwarnings('ignore')

# Page configuration
st.set_page_config(
    page_title="Electricity Demand Forecasting",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

from backend.features import add_engineered_features
from backend.modeling import calculate_metrics
from pathlib import Path
ROOT = Path(__file__).resolve().parent

# Load dataset and model
@st.cache_resource
def load_data():
    """Load the electricity demand dataset and engineer the required model features."""
    try:
        data = pd.read_excel(ROOT / 'data/electricity_demand_2025.xlsx')
        data = add_engineered_features(data)
        return data
    except FileNotFoundError:
        st.error("Dataset not found: data/electricity_demand_2025.xlsx")
        return None

@st.cache_resource
def load_model():
    """Load the trained XGBoost model"""
    try:
        model_package = joblib.load(ROOT / 'models/electricity_xgb_prediction_model.pkl')
        return model_package
    except FileNotFoundError:
        st.error("Model not found: models/electricity_xgb_prediction_model.pkl")
        return None

# Load data and model
data = load_data()
model_package = load_model()

if data is None or model_package is None:
    st.stop()

model = model_package['model']
features = model_package['features']
feature_importance_dict = model_package['feature_importance']

# Sidebar navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Select Page:",
    ["Overview", "Demand Analysis", "Model Performance", "Forecast"]
)

# ============================================================================
# PAGE: OVERVIEW
# ============================================================================
if page == "Overview":
    st.title("Electricity Demand Forecasting")
    
    st.markdown("""
    **IMPORTANT:** This dashboard uses a **SYNTHETIC (simulated) dataset** that represents 
    typical residential electricity consumption patterns. Results should NOT be used for 
    real-world decision-making without validation on actual data.
    """)
    
    # Dataset statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Observations",
            f"{len(data):,}",
            "Hourly readings"
        )
    
    with col2:
        st.metric(
            "Date Range",
            f"{data.index.min().strftime('%Y-%m-%d')}",
            f"to {data.index.max().strftime('%Y-%m-%d')}"
        )
    
    with col3:
        st.metric(
            "Avg Demand",
            f"{data['Demand'].mean():.2f} MW",
            f"± {data['Demand'].std():.2f} MW"
        )
    
    with col4:
        st.metric(
            "Peak Demand",
            f"{data['Demand'].max():.2f} MW",
            f"Min: {data['Demand'].min():.2f} MW"
        )
    
    # Demand over time
    st.subheader("Electricity Demand Over Time")
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data.index,
        y=data['Demand'],
        mode='lines',
        name='Demand',
        line=dict(color='steelblue', width=1)
    ))
    
    fig.update_layout(
        title="Historical Electricity Demand",
        xaxis_title="Date",
        yaxis_title="Demand (MW)",
        hovermode='x unified',
        height=500,
        template='plotly_white'
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Key statistics
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Demand Statistics")
        stats_df = pd.DataFrame({
            'Metric': ['Mean', 'Median', 'Std Dev', 'Min', 'Max', 'Q1', 'Q3'],
            'Value': [
                f"{data['Demand'].mean():.2f} MW",
                f"{data['Demand'].median():.2f} MW",
                f"{data['Demand'].std():.2f} MW",
                f"{data['Demand'].min():.2f} MW",
                f"{data['Demand'].max():.2f} MW",
                f"{data['Demand'].quantile(0.25):.2f} MW",
                f"{data['Demand'].quantile(0.75):.2f} MW",
            ]
        })
        st.dataframe(stats_df, use_container_width=True, hide_index=True)
    
    with col2:
        st.subheader("Temperature Statistics")
        stats_df = pd.DataFrame({
            'Metric': ['Mean', 'Median', 'Std Dev', 'Min', 'Max', 'Q1', 'Q3'],
            'Value': [
                f"{data['Temperature'].mean():.2f} C",
                f"{data['Temperature'].median():.2f} C",
                f"{data['Temperature'].std():.2f} C",
                f"{data['Temperature'].min():.2f} C",
                f"{data['Temperature'].max():.2f} C",
                f"{data['Temperature'].quantile(0.25):.2f} C",
                f"{data['Temperature'].quantile(0.75):.2f} C",
            ]
        })
        st.dataframe(stats_df, use_container_width=True, hide_index=True)

# ============================================================================
# PAGE: DEMAND ANALYSIS
# ============================================================================
elif page == "Demand Analysis":
    st.title("Demand Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Demand by Hour of Day")
        hourly = data.groupby('hour')['Demand'].mean().reset_index()
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hourly['hour'],
            y=hourly['Demand'],
            mode='lines+markers',
            name='Avg Demand',
            line=dict(color='coral', width=2),
            marker=dict(size=8),
            fill='tozeroy'
        ))
        
        fig.update_layout(
            xaxis_title="Hour",
            yaxis_title="Average Demand (MW)",
            height=400,
            template='plotly_white'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Demand by Month")
        monthly = data.groupby('month')['Demand'].mean().reset_index()
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=[month_names[int(m-1)] for m in monthly['month']],
            y=monthly['Demand'],
            name='Avg Demand',
            marker=dict(color='lightgreen')
        ))
        
        fig.update_layout(
            xaxis_title="Month",
            yaxis_title="Average Demand (MW)",
            height=400,
            template='plotly_white',
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Weekday vs Weekend")
        
        data_temp = data.copy()
        data_temp['is_weekend'] = data_temp.index.dayofweek.isin([5, 6])
        day_type_data = data_temp.groupby('is_weekend')['Demand'].mean().reset_index()
        day_type_data['Day Type'] = day_type_data['is_weekend'].map({False: 'Weekday', True: 'Weekend'})
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=day_type_data['Day Type'],
            y=day_type_data['Demand'],
            marker=dict(color=['steelblue', 'coral'])
        ))
        
        fig.update_layout(
            yaxis_title="Average Demand (MW)",
            height=400,
            template='plotly_white',
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Demand vs Temperature")
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=data['Temperature'],
            y=data['Demand'],
            mode='markers',
            marker=dict(size=3, color='darkviolet', opacity=0.5)
        ))
        
        fig.update_layout(
            xaxis_title="Temperature (C)",
            yaxis_title="Demand (MW)",
            height=400,
            template='plotly_white',
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Correlation
    st.subheader("Feature Correlations")
    correlation = data[['Demand', 'Temperature', 'Humidity', 'hour', 'dayofweek', 'month']].corr()
    
    fig = go.Figure(data=go.Heatmap(
        z=correlation.values,
        x=correlation.columns,
        y=correlation.columns,
        colorscale='RdBu',
        zmid=0,
        text=np.round(correlation.values, 2),
        texttemplate='%{text}',
        textfont={"size": 10}
    ))
    
    fig.update_layout(
        height=500,
        xaxis_title="Feature",
        yaxis_title="Feature"
    )
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# PAGE: MODEL PERFORMANCE
# ============================================================================
elif page == "Model Performance":
    st.title("Model Performance")
    
    st.caption("Training through 2022; early stopping on 2023; final held-out test on 2024. Synthetic local demo.")
    # Split data chronologically
    split_date = pd.Timestamp('2024-01-01')
    val_data = data.loc[split_date:model_package['test_period']['end']].dropna(subset=features + ['Demand']).copy()
    X_val = val_data[features]
    y_val = val_data['Demand']
    
    # Make predictions
    if len(X_val) > 0 and all(col in X_val.columns for col in features):
        X_val = X_val.dropna()
        y_val = y_val.loc[X_val.index]
        y_pred = model.predict(X_val)
        
        # Metrics
        metrics = calculate_metrics(y_val, y_pred)
        
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("MAE", f"{metrics['mae']:.2f} MW", "Mean Absolute Error")
        
        with col2:
            st.metric("RMSE", f"{metrics['rmse']:.2f} MW", "Root Mean Squared Error")
        
        with col3:
            st.metric("R2 Score", f"{metrics['r2']:.4f}", f"Explains {metrics['r2']*100:.1f}% of variance")
        
        with col4:
            st.metric("WAPE", f"{metrics['wape']:.2f}%", "Weighted Absolute % Error")
        
        # Actual vs Predicted
        st.subheader("Actual vs Predicted Demand")
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=y_val.index,
            y=y_val.values,
            mode='lines',
            name='Actual',
            line=dict(color='steelblue', width=1.5)
        ))
        fig.add_trace(go.Scatter(
            x=y_val.index,
            y=y_pred,
            mode='lines',
            name='Predicted',
            line=dict(color='red', width=1.5, dash='dash')
        ))
        
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Demand (MW)",
            height=500,
            template='plotly_white'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Error distribution
        st.subheader("Error Distribution")
        
        errors = y_val.values - y_pred
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=errors,
                nbinsx=50,
                name='Errors',
                marker=dict(color='steelblue')
            ))
            
            fig.update_layout(
                xaxis_title="Error (MW)",
                yaxis_title="Frequency",
                height=400,
                template='plotly_white'
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=y_val.values,
                y=y_pred,
                mode='markers',
                marker=dict(size=4, color='steelblue', opacity=0.5)
            ))
            
            # Add perfect prediction line
            min_val = min(y_val.min(), y_pred.min())
            max_val = max(y_val.max(), y_pred.max())
            fig.add_trace(go.Scatter(
                x=[min_val, max_val],
                y=[min_val, max_val],
                mode='lines',
                name='Perfect',
                line=dict(color='red', dash='dash')
            ))
            
            fig.update_layout(
                xaxis_title="Actual Demand (MW)",
                yaxis_title="Predicted Demand (MW)",
                height=400,
                template='plotly_white'
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        # Feature importance
        st.subheader("Feature Importance")
        
        importance_df = pd.DataFrame({
            'Feature': list(feature_importance_dict.keys()),
            'Importance': list(feature_importance_dict.values())
        }).sort_values('Importance', ascending=True).tail(15)
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=importance_df['Importance'],
            y=importance_df['Feature'],
            orientation='h',
            marker=dict(color='steelblue')
        ))
        
        fig.update_layout(
            xaxis_title="Importance Score",
            height=500,
            template='plotly_white',
            showlegend=False
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("Unable to generate predictions. Feature mismatch or insufficient data.")

# ============================================================================
# PAGE: FORECAST
# ============================================================================
elif page == "Forecast":
    st.title("Make a Prediction")
    
    st.markdown("""
    **Forecast Limitations:**
    - This tool demonstrates model predictions on historical data
    - Real forecasts require recent observed demand matching the stored feature schema and a weather forecast
    - The model is trained on SYNTHETIC data and not suitable for real-world use
    """)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Select a date for demonstration
        forecast_date = st.date_input(
            "Select a date to demonstrate prediction:",
            value=data.index.max().date() - timedelta(days=30),
            min_value=data.dropna(subset=features).index.min().date(),
            max_value=data.index.max().date()
        )
        
        forecast_hour = st.slider(
            "Select hour of day:",
            0, 23, 12
        )
    
    with col2:
        st.info(f"{forecast_date.strftime('%A, %B %d, %Y')} at {forecast_hour:02d}:00")
    
    # Create timestamp and get features
    try:
        timestamp = pd.Timestamp(f"{forecast_date} {forecast_hour:02d}:00:00")
        
        if timestamp in data.index:
            row = data.loc[[timestamp]]
            actual = row['Demand'].values[0]
            
            # Make prediction
            X_sample = row[features]
            prediction = model.predict(X_sample)[0]
            
            # Display results
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Actual Demand", f"{actual:.2f} MW", "From historical data")
            
            with col2:
                st.metric("Predicted Demand", f"{prediction:.2f} MW", f"Error: {abs(actual - prediction):.2f} MW")
            
            # Show input features
            st.subheader("Input Features for This Prediction")
            
            feature_values = pd.DataFrame({
                'Feature': X_sample.columns,
                'Value': X_sample.values[0]
            })
            
            st.dataframe(feature_values, use_container_width=True, hide_index=True)
            
            # Context
            st.subheader("Context")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write(f"**Temperature:** {row['Temperature'].values[0]:.1f} C")
                st.write(f"**Humidity:** {row['Humidity'].values[0]:.1f} %")
            
            with col2:
                day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                dow = int(row['dayofweek'].values[0])
                st.write(f"**Day:** {day_names[dow]}")
                st.write(f"**Hour:** {int(row['hour'].values[0]):02d}:00")
            
            with col3:
                is_holiday = "YES - Holiday" if row.get('is_holiday', pd.Series([0])).values[0] else "Regular Day"
                is_weekend = "YES - Weekend" if row.get('is_weekend', pd.Series([0])).values[0] else "Weekday"
                st.write(f"**Day Type:** {is_weekend}")
                st.write(f"**Holiday:** {is_holiday}")
        
        else:
            st.warning(f"No data available for {timestamp}. Please select a different date.")
    
    except Exception as e:
        st.error(f"Error making prediction: {str(e)}")
    
    # Information
    st.markdown("""
    ---
    ### How This Works
    
    1. **Feature Extraction**: The model extracts time-based features (hour, day, month, etc.)
    2. **Historical Features**: Uses only demand observed before the prediction timestamp
    3. **Weather Features**: Temperature and humidity from the selected time
    4. **Prediction**: XGBoost combines all features to forecast demand
    
    ### Limitations
    - Best supported for one-step-ahead / short-horizon use
    - Multi-hour recursive forecasts are experimental; predicted demand feeds later lags, so errors accumulate
    - Requires historical data: Cannot forecast if recent demand is unknown
    - Synthetic data: Results not validated on real electricity data
    """)

# Footer
st.markdown("""
---
<div style='text-align: center; padding: 20px; color: #666;'>
    <small>Electricity Demand Forecasting Dashboard | XGBoost Model | Streamlit Application</small>
</div>
""", unsafe_allow_html=True)

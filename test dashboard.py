import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely import wkt
import pydeck as pdk

# Cache the data loading for performance
@st.cache
def load_data():
    # Adjust the file path if necessary
    df = pd.read_csv("test_pressure_time_small.csv")
    # Convert the geometry column from WKT string to a shapely geometry object
    df['geometry'] = df['geometry'].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
    # Extract latitude and longitude for mapping
    gdf['lat'] = gdf.geometry.y
    gdf['lon'] = gdf.geometry.x
    # Convert the datetime column to a datetime type
    gdf['datetime'] = pd.to_datetime(gdf['datetime'])
    return gdf

data = load_data()

# Sidebar: Add a slider for selecting a specific date and hour
min_date = data['datetime'].min()
max_date = data['datetime'].max()
selected_time = st.slider(
    "Select Date and Hour",
    min_value=min_date,
    max_value=max_date,
    value=min_date,
    format="YYYY-MM-DD HH:00:00"
)

# Filter the data for the selected time
data_selected = data[data['datetime'] == selected_time]

st.subheader("Tourist Pressure Map")

# Using pydeck for a more interactive map that allows zooming
if not data_selected.empty:
    view_state = pdk.ViewState(
        latitude=data_selected['lat'].mean(), 
        longitude=data_selected['lon'].mean(),
        zoom=12, pitch=0
    )
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=data_selected,
        get_position='[lon, lat]',
        get_color='[255, 0, 0, 140]',
        get_radius='pressure',  # This assumes the pressure value can scale the point size
        pickable=True,
    )
    tooltip = {"html": "Pressure: {pressure}", "style": {"color": "white"}}
    deck = pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip)
    st.pydeck_chart(deck)
else:
    st.write("No data available for the selected time.")

st.subheader("Pressure Over Time")

# For the line chart, aggregate pressure values over time (here, using the mean)
pressure_over_time = data.groupby('datetime')['pressure'].mean().reset_index()
pressure_over_time = pressure_over_time.sort_values("datetime")
pressure_over_time = pressure_over_time.set_index("datetime")
st.line_chart(pressure_over_time)

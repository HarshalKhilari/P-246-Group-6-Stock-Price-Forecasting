import os, sys

import pandas as pd

# import plotly package for graphs
import plotly
import plotly.graph_objs as go
import plotly.express as px
from plotly.subplots import make_subplots

import yfinance as yf

from requests import Session
from requests_cache import CacheMixin, SQLiteCache
from requests_ratelimiter import LimiterMixin, MemoryQueueBucket
from pyrate_limiter import Duration, RequestRate, Limiter

# CachedLimiterSession class extends the CacheMixin, LimiterMixin, and Session classes.
# This class combines request caching (SQLiteCache) and rate limiting (Limiter) functionalities to prevent excessive API requests.
class CachedLimiterSession(CacheMixin, LimiterMixin, Session):
    pass

# An instance of CachedLimiterSession is created as session with a rate limit of 2 requests per 5 seconds and a caching backend using SQLite.
session = CachedLimiterSession(
    limiter=Limiter(RequestRate(2, Duration.SECOND*5)),  # max 2 requests per 5 seconds
    bucket_class=MemoryQueueBucket,
    backend=SQLiteCache("yfinance.cache")
    )

# suppresses the output to the standard output stream (stdout). 
# This class is used to silence the printing of unwanted information during the execution of the script.
class HiddenPrints:
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout


def plot_stock_data(stock, hist):
    # Input: yfinance stock ticker, dataframe of historical data
    # Provides interactive plot of the Open and Close stock prices

    # Create a plotly figure graphical object
    fig = go.Figure()
    # Add Scatter plots for Open and Close prices
    fig.add_trace(go.Scatter(x=hist.index, y=hist.Open, name="Stock Open"))
    fig.add_trace(go.Scatter(x=hist.index, y=hist.Close, name="Stock Close"))
    # Plotting Stock name as plot title (from stock ticker) with range slider for time
    fig.layout.update(title_text=f"{stock.info['longName']} Stock Price", width = 1150, height = 600, xaxis_rangeslider_visible=True)
    # Show plot
    fig.show()






import streamlit as st
from plotly import graph_objs as go

st.title('Stock Price Forecasting App')


# Code to get a dataframe of the historical stock data
# Take ticker symbol from user
symbol = st.text_input('Enter Stock ticker: ')

# Create a yfinance ticker object for user-defined symbol and using a session for rate-limiting and request caching
stock = yf.Ticker(symbol, session=session)
# If symbol is invalid, yfinance prints a long message regarding unavailability of the data and possible reasons, and returns an empty dataframe
# To supress this message, we use HiddenPrints class
with HiddenPrints():
    # Get entire available stock data using yfinance for user-defined symbol
    hist = stock.history(period="max")
# If dataframe is empty, we print a message regarding unavailability of data
if hist.shape[0] == 0:
    print("No data found. Symbol is not listed.")
# Dropping Dividends and Stock Splits columns as Dividends are very rare and price changes after Stock Splits are accounted for in yahoo finance
hist = hist[['Close']]
# If historical data is retrieved, we print the dataframe


def calculate_directional_accuracy(actual_prices, predicted_prices):
    # Ensure the lengths of actual_prices and predicted_prices are the same
    if len(actual_prices) != len(predicted_prices):
        raise ValueError("Lengths of actual_prices and predicted_prices must be the same.")

    correct_predictions = 0
    total_predictions = len(actual_prices) - 1  # Exclude the first price for direction comparison

    for i in range(1, len(actual_prices)):
        actual_direction = actual_prices[i] - actual_prices[i-1]
        predicted_direction = predicted_prices[i] - actual_prices[i-1]

        if (actual_direction >= 0 and predicted_direction >= 0) or (actual_direction < 0 and predicted_direction < 0):
            correct_predictions += 1

    directional_accuracy = correct_predictions / total_predictions

    return directional_accuracy



def get_forecast(hist, validation_days = 365, days_to_forecast = 30):

    # Getting the latest date from the dataframe
    last_day = hist.index[-1]
    first_day = last_day - relativedelta(years = 5)

    # Getting the last training day based on the passed valudation days
    last_train_day = last_day - relativedelta(days = validation_days)

    # Getting training and testing test
    y_train = hist.loc[first_day:last_train_day, 'Close']
    y_test = hist.loc[last_train_day:, 'Close']

    all_days = hist.loc[first_day:, 'Close']

    # Getting the last forecast day
    last_forecast_day = last_day + relativedelta(days = days_to_forecast)

    # Getting data range for forecast days
    forecast_days = pd.date_range(start = last_day + relativedelta(days = 1), end = last_forecast_day, freq="B").tolist()

    
    fc_arima, errors_arima = auto_arima_model(y_train, y_test, forecast_days)
    fc_lstm, errors_lstm = lstm_model(y_train, y_test, forecast_days)
    fc_mcmc, errors_mcmc = MCMC_model(y_train, y_test, forecast_days)

    error_df = pd.DataFrame([errors_arima, errors_lstm, errors_mcmc], index = ['ARIMA', 'LSTM', 'MCMC'])
    
    print(error_df)
    print(fc_arima.shape, fc_lstm.shape, fc_mcmc.shape)

    # fc_final = multi_model_avg()
    arima_pred = fc_arima.fc.values.tolist()
    lstm_pred = fc_lstm.values.tolist()
    mcmc_pred = fc_mcmc.values.tolist()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(range(all_days.shape[0])), y=all_days.values.tolist(), mode='lines+markers', line=dict(color='#39304A', width=5),
                             marker=dict(color='#39304A', size=10),  name='historical'))
    fig.add_trace(go.Scatter(x=list(range(len(lstm_pred))), y=lstm_pred, mode='lines+markers', 
                             line=dict(color='#FF6601'), name='LSTM'))
    fig.add_trace(go.Scatter(x=list(range(len(mcmc_pred))), y=mcmc_pred, mode='lines+markers', 
                             line=dict(color='#CB000A'), name='MCMC'))
    fig.add_trace(go.Scatter(x=list(range(len(arima_pred))), y=arima_pred, mode='lines+markers', 
                             line=dict(color='#FFDB2D'), name='ARIMA'))
    
    fig.update_layout(legend_orientation="h",
                      legend=dict(x=.5, xanchor="center"),
                      plot_bgcolor='#FFFFFF',  
                      xaxis=dict(gridcolor = 'lightgrey'),
                      yaxis=dict(gridcolor = 'lightgrey'),
                      title_text = 'predictions', title_x = 0.5,
                      xaxis_title="Timestep",
                      yaxis_title="Stock price",
                      width = 1150, 
                      height = 600,
                      margin=dict(l=0, r=0, t=30, b=0))
    fig.show()
    st.plotly_chart(fig)


import pmdarima as pm
from pmdarima.arima import ndiffs, nsdiffs
from dateutil.relativedelta import relativedelta
from sklearn.metrics import mean_squared_error
from pmdarima.metrics import smape

def auto_arima_model(y_train, y_test, forecast_days):
    
    # Creating a dataframe to store forecasts
    fc_df = pd.DataFrame(columns = ['fc', 'conf_low', 'conf_high'], index = forecast_days)

    auto = pm.auto_arima(
                     y = y_train, 
                     start_p = 1,
                     start_q = 1,
                     max_order = None,
                     seasonal=False, 
                     stepwise=False,
                     maxiter = 100,
                     suppress_warnings=True, 
                     error_action="ignore",
                     trace=True, 
                     n_jobs = -1
                        )

    model = auto  # seeded from the model we've already fit

    def validate_and_update():
        fc, conf_int = model.predict(n_periods=1, return_conf_int=True)
        return (fc.tolist()[0], np.asarray(conf_int).tolist()[0])
    
    forecasts = []
    confidence_intervals = []
    
    for date, price in y_test.items():
        #new_obs = pd.Series([price], index = [date], name = 'Close')
        fc, conf = validate_and_update()
        forecasts.append(fc)
        confidence_intervals.append(conf)
        # Updates the existing model with a small number of MLE steps
        model.update(pd.Series([price], index = [date], name = 'Close'))
    
    errors = {
        "Mean squared error": mean_squared_error(y_test, forecasts),
        "SMAPE": smape(y_test, forecasts),
        "DA": calculate_directional_accuracy(y_test, forecasts)
    }
    
    def forecast_one_month():
        fc, conf_int = model.predict(n_periods=fc_df.shape[0], return_conf_int=True)
        return (
            fc.tolist(),
            np.asarray(conf_int).tolist())
    
    fc, conf = forecast_one_month()
    i=0
    for new_day in fc_df.index.tolist():
        fc_df.loc[new_day, 'fc'] = fc[i]
        fc_df.loc[new_day, 'conf_low'] = conf[i][0]
        fc_df.loc[new_day, 'conf_high'] = conf[i][1]
        i+=1
    
    return fc_df, errors




from sklearn.preprocessing import MinMaxScaler
import math
import matplotlib.pyplot as plt
import keras
import pandas as pd
import numpy as np
from keras.models import Sequential
from keras.layers import Dense
from keras.layers import LSTM
from keras.layers import Dropout
from keras.layers import *
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
from keras.callbacks import EarlyStopping
from keras.models import Sequential
from keras.layers import Dense, LSTM

def lstm_model(y_train, y_test, forecast_days):

    trainset = y_train.values
    testset = y_test.values

    # Scale our data from 0 to 1
    scaler = MinMaxScaler(feature_range=(0,1))
    scaler.fit(np.concatenate((trainset, testset), axis=0).reshape(-1, 1))
    y_train_scaled = scaler.transform(trainset.reshape(-1, 1))
    y_test_scaled = scaler.transform(testset.reshape(-1, 1))
    
    # Use our scaled data for training
    train_X = []
    train_y = []

    for i in range(60, len(y_train_scaled)):
        train_X.append(y_train_scaled[i-60:i, 0])
        train_y.append(y_train_scaled[i, 0])

    train_X, train_y = np.array(train_X), np.array(train_y)

    train_X = np.reshape(train_X, (train_X.shape[0], train_X.shape[1], 1))
    
    # Build LSTM model
    model = Sequential()
    model.add(LSTM(128, return_sequences=True, input_shape = (train_X.shape[1], 1)))
    model.add(Dropout(0.35))
    model.add(LSTM(64, return_sequences=False))
    model.add(Dropout(0.3))
    model.add(Dense(25, activation = 'relu'))
    model.add(Dense(1))
    
    # Compile the model
    model.compile(optimizer='adam', loss='mean_squared_error', metrics=['accuracy'])

    # Тrain the model
    model.fit(train_X, train_y, batch_size=1, epochs=20)
    
    # Structure of the model
    keras.utils.plot_model(model, 'multi_input_and_output_model.png', show_shapes=True)

    y_test_scaled = np.concatenate([y_train_scaled[-60:], y_test_scaled], axis = 0)
    
    # Create test dataset
    test_X = []
    for i in range(60, len(y_test_scaled)):
        test_X.append(y_test_scaled[i-60:i, 0])

    test_X = np.array(test_X)

    test_X = np.reshape(test_X, (test_X.shape[0], test_X.shape[1], 1 ))

    # Predict on test data
    predictions = model.predict(test_X)
    predictions = scaler.inverse_transform(predictions)

    errors = {
        "Mean squared error": mean_squared_error(y_test, predictions),
        "SMAPE": smape(y_test, predictions),
        "DA": calculate_directional_accuracy(y_test, predictions)
    }
    

    # Predict the stock prices for the forecast interval
    last_sequence = test_X[-1]  # Use the last sequence from the training data
    forecast = []

    for _ in range(len(forecast_days)):
        next_pred = model.predict(last_sequence.reshape(1, 60, -1))
        forecast.append(next_pred[0])
        last_sequence = np.append(last_sequence[1:], next_pred[0])

    # Inverse transform the forecasted data to obtain actual stock prices
    forecast = scaler.inverse_transform(np.array(forecast).reshape(-1, 1))

    # Creating a dataframe to store forecasts
    fc_df = pd.DataFrame(columns = ['fc'], index = forecast_days)

    i=0
    for new_day in fc_df.index.tolist():
        fc_df.loc[new_day, 'fc'] = forecast[i]
        i+=1
    
    return fc_df, errors



import numpy as np
import math
from numpy import linalg as la
import matplotlib.pyplot as plt
import math
import pandas as pd
import yfinance as yf
import statistics as stat
from scipy.special import ndtri
from scipy.stats import norm
import random
from sklearn.metrics import mean_squared_error

mu, sig, N = 1.1, 1, 1000
pts = []


def q(x):
    return (1 / (math.sqrt(2 * math.pi * sig ** 2))) * (math.e ** (-((x - mu) ** 2) / (2 * sig ** 2)))

def MCMC(n):
    r = np.zeros(1)
    p = q(r[0])
    pts = []

    for i in range(N):
        rn = r + np.random.uniform(-1, 1)
        pn = q(rn[0])
        if pn >= p:
            p = pn
            r = rn
        else:
            u = np.random.rand()
            if u < pn / p:
                p = pn
                r = rn
        pts.append(r)

    pts = random.sample(pts, len(pts))
    pts = np.array(pts)
    
    return pts

def MH(y_train, y_test, is_forecast = False):
    y_test = np.array(y_test)
    stock_pred = []
    maturnity = 1
    volatility = 0.25
    risk_free = 0.1
    timestep = 1
    steps = len(y_test)
    delta_t = maturnity / steps
    i = 0
    stock_pred.append(y_train[-1])
    while timestep < steps:
        stock_price = stock_pred[-i]
        time_exp = maturnity - delta_t * timestep
        # Generate z_t using MCMC method
        pts = MCMC(N)
        stock_price = stock_price * math.exp(((risk_free - 0.5 * (
            math.pow(volatility, 2))) * delta_t + volatility * math.sqrt(delta_t) * pts[timestep + 5]))
        stock_pred.append(stock_price)
        i = i + 1
        timestep = timestep + 1
    print(y_test.shape, np.array(stock_pred).shape)
    if not is_forecast:
        errors = {
        "Mean squared error": mean_squared_error(y_test, stock_pred),
        "SMAPE": smape(y_test, stock_pred),
        "DA": calculate_directional_accuracy(y_test, stock_pred)
        }
    else:
        errors = np.nan
    
    return errors, stock_pred
    
    
def MCMC_model(y_train, y_test, forecast_days):

    # Creating a dataframe to store forecasts
    fc_df = pd.DataFrame(columns = ['fc'], index = forecast_days)
    
    val_errors, val_pred = MH(y_train, y_test)
    hist_data = np.concatenate((trainset, testset), axis=0).flatten()
    
    errors, forecast = MH(hist_data, fc_df, is_forecast = True)
    
    i=0
    for new_day in fc_df.index.tolist():
        fc_df.loc[new_day, 'fc'] = forecast[i]
        i+=1
    
    return fc_df, val_errors



get_forecast(hist)
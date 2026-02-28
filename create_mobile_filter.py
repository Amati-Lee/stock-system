"""
create_mobile_filter_ios.py
手機優化版（含 AND/OR 邏輯 + 全局參數篩選）
"""
import pandas as pd
import json
from datetime import datetime
import glob

def get_latest_data_file():
    files = glob.glob("stock_data_*.csv")
    return max(files) if files else None

print("=" * 70)
print("  打包股票數據為手機版（含全局參數）")
print("=" * 70)
print()

data_file = get_latest_data_file()
if not data_file:
    print("❌ 找不到數據檔案")
    exit(1)

print(f"📁 載入：{data_file}")
df = pd.read_csv(data_file, encoding="utf-8-sig")
print(f"   總筆數：{len(df)}")

essential_cols = [
    "股票代號", "股票名稱", "收盤價", 
    "K值", "D值", "KD狀態",
    "RSI", "MACD狀態", "BB位置",
    "成交量張", "量比", "市值億", "本益比", "殖利率", "EPS"
]

df_essential = df[essential_cols].fillna('')
json_data = df_essential.to_json(orient='records', force_ascii=False)

print(f"📊 大小：{len(json_data)/1024:.1f} KB")
print()
html_template = '''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>台股篩選器</title>
<style>
* {margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body {font-family:-apple-system,BlinkMacSystemFont,"Microsoft JhengHei",sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:10px}
.container {max-width:800px;margin:0 auto}
.card {background:white;border-radius:15px;padding:15px;margin-bottom:15px;box-shadow:0 4px 6px rgba(0,0,0,0.1)}
h1 {font-size:24px;color:#333;margin-bottom:5px}
.info {color:#666;font-size:14px;margin-bottom:10px}
.section-title {font-size:14px;font-weight:bold;color:#667eea;margin:15px 0 8px 0}
.btn {display:inline-block;background:#f0f0f0;color:#333;padding:12px 16px;margin:5px 5px 5px 0;border-radius:8px;border:2px solid transparent;font-size:15px;cursor:pointer;user-select:none;touch-action:manipulation}
.btn.active {background:#667eea;color:white;border-color:#667eea}
.logic-box {background:#f8f8f8;padding:12px;border-radius:8px;margin:15px 0}
.logic-box label {display:flex;align-items:center;margin:8px 0;cursor:pointer}
.logic-box input[type="radio"] {margin-right:8px;width:18px;height:18px}
.input-group {margin:10px 0}
.input-group label {display:block;font-size:14px;color:#666;margin-bottom:5px}
.input-group input {width:100%;padding:12px;border:2px solid #e0e0e0;border-radius:8px;font-size:16px}
.input-row {display:grid;grid-template-columns:1fr 1fr;gap:10px}
.main-btn {width:100%;padding:16px;background:#667eea;color:white;border:none;border-radius:10px;font-size:16px;font-weight:bold;cursor:pointer;margin-top:10px}
.stock-item {background:#f8f8f8;border-radius:10px;padding:12px;margin-bottom:10px;border-left:4px solid #667eea}
.stock-header {display:flex;justify-content:space-between;margin-bottom:8px}
.stock-code {font-size:16px;font-weight:bold}
.stock-price {font-size:18px;font-weight:bold;color:#e74c3c}
.stock-details {display:grid;grid-template-columns:repeat(2,1fr);gap:5px;font-size:13px;color:#666}
.hidden {display:none}
.divider {height:1px;background:#e0e0e0;margin:15px 0}
.checkbox-group {margin:10px 0}
.checkbox-group label {display:flex;align-items:center;padding:10px;font-size:15px;color:#333}
.checkbox-group input[type="checkbox"] {margin-right:10px;width:20px;height:20px}
.view-toggle {display:flex;gap:5px;margin-bottom:10px}
.view-btn {flex:1;padding:12px;background:#f0f0f0;border:none;border-radius:8px;font-size:15px;cursor:pointer}
.view-btn.active {background:#667eea;color:white}
.table-container {overflow-x:auto;-webkit-overflow-scrolling:touch}
.stock-table {width:100%;border-collapse:collapse;font-size:13px;min-width:900px}
.stock-table th {background:#667eea;color:white;padding:12px 8px;text-align:left;position:sticky;top:0;cursor:pointer;user-select:none;white-space:nowrap}
.stock-table th.sortable::after {content:" ↕";opacity:0.5}
.stock-table th.sorted-asc::after {content:" ↑";opacity:1}
.stock-table th.sorted-desc::after {content:" ↓";opacity:1}
.stock-table td {padding:10px 8px;border-bottom:1px solid #e0e0e0;white-space:nowrap}
.stock-table tr:nth-child(even) {background:#f8f8f8}
.global-hint {font-size:12px;color:#999;font-style:italic}
</style>
</head>
<body>
<div class="container">
<div class="card">
<h1>📊 台股篩選器</h1>
<div class="info">更新：UPDATETIME | 總筆數：TOTALCOUNT</div>
</div>

<div class="card">
<div class="section-title">📍 策略選擇（可複選）</div>

<div style="margin-bottom:10px;font-size:14px;color:#666">長線投資</div>
<div class="btn" data-strategy="dividend">高殖利率</div>
<div class="btn" data-strategy="value">價值投資</div>

<div style="margin-bottom:10px;margin-top:15px;font-size:14px;color:#666">短線操作</div>
<div class="btn" data-strategy="kd_golden">KD黃金交叉</div>
<div class="btn" data-strategy="bb_upper">布林上軌</div>
<div class="btn" data-strategy="macd_golden">MACD黃金交叉</div>

<div style="margin-bottom:10px;margin-top:15px;font-size:14px;color:#666">超賣反彈</div>
<div class="btn" data-strategy="kd_oversold">KD超賣</div>
<div class="btn" data-strategy="rsi_oversold">RSI超賣</div>
<div class="btn" data-strategy="bb_lower">布林下軌</div>

<div id="params" class="hidden">
<div class="divider"></div>

<div class="logic-box">
<div style="font-weight:bold;margin-bottom:8px;color:#333">策略組合方式：</div>
<label>
<input type="radio" name="logicMode" value="or" checked>
<span>OR（任一符合）- 結果較多</span>
</label>
<label>
<input type="radio" name="logicMode" value="and">
<span>AND（全部符合）- 結果較少</span>
</label>
</div>

<div class="section-title">⚙️ 策略參數</div>

<div class="input-row">
<div class="input-group">
<label>最低殖利率（%）</label>
<input type="number" id="minDiv" value="5" step="0.5">
</div>
<div class="input-group">
<label>最高本益比</label>
<input type="number" id="maxPE" value="20" step="1">
</div>
</div>

<div class="input-row">
<div class="input-group">
<label>K值上限</label>
<input type="number" id="maxK" value="20" step="1">
</div>
<div class="input-group">
<label>RSI上限</label>
<input type="number" id="maxRSI" value="30" step="1">
</div>
</div>

<div class="divider"></div>
<div class="section-title">🔍 額外篩選（可選）</div>
<div class="global-hint">※ 以下條件為全局篩選，無論選什麼策略都會生效</div>

<div class="checkbox-group">
<label>
<input type="checkbox" id="usePrice">
價格範圍
</label>
</div>
<div id="priceInputs" class="input-row hidden">
<div class="input-group">
<label>最低價格（元）</label>
<input type="number" id="minPrice" value="10" step="1">
</div>
<div class="input-group">
<label>最高價格（元）</label>
<input type="number" id="maxPrice" value="300" step="10">
</div>
</div>

<div class="checkbox-group">
<label>
<input type="checkbox" id="useCap">
市值範圍
</label>
</div>
<div id="capInputs" class="input-row hidden">
<div class="input-group">
<label>最低市值（億）</label>
<input type="number" id="minCap" value="10" step="10">
</div>
<div class="input-group">
<label>最高市值（億）</label>
<input type="number" id="maxCap" value="1000" step="100">
</div>
</div>

<div class="checkbox-group">
<label>
<input type="checkbox" id="useVolume">
量比篩選
</label>
</div>
<div id="volumeInputs" class="input-group hidden">
<label>最低量比（倍數）</label>
<input type="number" id="minVolume" value="1.5" step="0.1">
</div>

<div class="checkbox-group">
<label>
<input type="checkbox" id="useDividend">
殖利率篩選（全局）
</label>
</div>
<div id="dividendInputs" class="input-group hidden">
<label>最低殖利率（%）</label>
<input type="number" id="globalMinDiv" value="3.5" step="0.5">
</div>

<div class="checkbox-group">
<label>
<input type="checkbox" id="usePE">
本益比上限（全局）
</label>
</div>
<div id="peInputs" class="input-group hidden">
<label>最高本益比</label>
<input type="number" id="globalMaxPE" value="20" step="1">
</div>

<div class="checkbox-group">
<label>
<input type="checkbox" id="useRSI">
RSI上限（全局）
</label>
</div>
<div id="rsiInputs" class="input-group hidden">
<label>RSI上限</label>
<input type="number" id="globalMaxRSI" value="91" step="1">
</div>

<div class="checkbox-group">
<label>
<input type="checkbox" id="useK">
K值範圍（全局）
</label>
</div>
<div id="kInputs" class="input-row hidden">
<div class="input-group">
<label>最低K值</label>
<input type="number" id="globalMinK" value="0" step="5">
</div>
<div class="input-group">
<label>最高K值</label>
<input type="number" id="globalMaxK" value="100" step="5">
</div>
</div>

<div class="checkbox-group">
<label>
<input type="checkbox" id="useEPS">
EPS篩選（全局）
</label>
</div>
<div id="epsInputs" class="input-group hidden">
<label>最低EPS（元）</label>
<input type="number" id="globalMinEPS" value="1" step="0.5">
</div>

</div>

<button class="main-btn" id="filterBtn">🔍 開始篩選</button>
</div>

<div id="results" class="hidden">
<div class="card">
<div style="margin-bottom:15px">
<div style="font-weight:bold;font-size:18px">找到 <span id="count">0</span> 筆</div>
</div>

<div class="view-toggle">
<button class="view-btn active" id="cardViewBtn">📱 卡片檢視</button>
<button class="view-btn" id="tableViewBtn">📊 表格檢視</button>
</div>

<div id="cardView">
<div id="list"></div>
</div>

<div id="tableView" class="hidden">
<div class="table-container">
<table class="stock-table">
<thead>
<tr>
<th class="sortable" data-col="股票代號">代號</th>
<th class="sortable" data-col="股票名稱">名稱</th>
<th class="sortable" data-col="收盤價">價格</th>
<th class="sortable" data-col="K值">K值</th>
<th class="sortable" data-col="D值">D值</th>
<th class="sortable" data-col="RSI">RSI</th>
<th class="sortable" data-col="BB位置">BB位置</th>
<th class="sortable" data-col="成交量張">成交量</th>
<th class="sortable" data-col="量比">量比</th>
<th class="sortable" data-col="殖利率">殖利率</th>
<th class="sortable" data-col="本益比">本益比</th>
<th class="sortable" data-col="EPS">EPS</th>
<th class="sortable" data-col="市值億">市值</th>
</tr>
</thead>
<tbody id="tableBody">
</tbody>
</table>
</div>
</div>

<button class="main-btn" id="exportBtn" style="background:#27ae60;margin-top:10px">📥 下載 CSV</button>
</div>
</div>
</div>

<script>
var stockData = DATAPLACEHOLDER;
var selectedStrategies = [];
var filteredData = [];
var currentView = 'card';
var sortColumn = null;
var sortDirection = 'asc';

window.addEventListener('load', function() {
    console.log('載入完成，股票數：' + stockData.length);
    
    var strategyBtns = document.querySelectorAll('.btn[data-strategy]');
    for (var i = 0; i < strategyBtns.length; i++) {
        strategyBtns[i].addEventListener('click', function() {
            var strategy = this.getAttribute('data-strategy');
            var index = selectedStrategies.indexOf(strategy);
            
            if (index >= 0) {
                selectedStrategies.splice(index, 1);
                this.classList.remove('active');
            } else {
                selectedStrategies.push(strategy);
                this.classList.add('active');
            }
            
            document.getElementById('params').className = selectedStrategies.length > 0 ? '' : 'hidden';
        });
    }
    
    document.getElementById('usePrice').addEventListener('change', function() {
        document.getElementById('priceInputs').className = this.checked ? 'input-row' : 'input-row hidden';
    });
    document.getElementById('useCap').addEventListener('change', function() {
        document.getElementById('capInputs').className = this.checked ? 'input-row' : 'input-row hidden';
    });
    document.getElementById('useVolume').addEventListener('change', function() {
        document.getElementById('volumeInputs').className = this.checked ? 'input-group' : 'input-group hidden';
    });
    document.getElementById('useDividend').addEventListener('change', function() {
        document.getElementById('dividendInputs').className = this.checked ? 'input-group' : 'input-group hidden';
    });
    document.getElementById('usePE').addEventListener('change', function() {
        document.getElementById('peInputs').className = this.checked ? 'input-group' : 'input-group hidden';
    });
    document.getElementById('useRSI').addEventListener('change', function() {
        document.getElementById('rsiInputs').className = this.checked ? 'input-group' : 'input-group hidden';
    });
    document.getElementById('useK').addEventListener('change', function() {
        document.getElementById('kInputs').className = this.checked ? 'input-row' : 'input-row hidden';
    });
    document.getElementById('useEPS').addEventListener('change', function() {
        document.getElementById('epsInputs').className = this.checked ? 'input-group' : 'input-group hidden';
    });
    
    document.getElementById('filterBtn').addEventListener('click', doFilter);
    document.getElementById('cardViewBtn').addEventListener('click', function() {
        switchView('card');
    });
    document.getElementById('tableViewBtn').addEventListener('click', function() {
        switchView('table');
    });
    document.getElementById('exportBtn').addEventListener('click', exportCSV);
    
    var sortHeaders = document.querySelectorAll('.stock-table th.sortable');
    for (var i = 0; i < sortHeaders.length; i++) {
        sortHeaders[i].addEventListener('click', function() {
            var column = this.getAttribute('data-col');
            
            if (sortColumn === column) {
                sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                sortColumn = column;
                sortDirection = 'asc';
            }
            
            filteredData.sort(function(a, b) {
                var valA = a[column] || 0;
                var valB = b[column] || 0;
                
                if (typeof valA === 'string') valA = valA.toLowerCase();
                if (typeof valB === 'string') valB = valB.toLowerCase();
                
                if (sortDirection === 'asc') {
                    return valA > valB ? 1 : valA < valB ? -1 : 0;
                } else {
                    return valA < valB ? 1 : valA > valB ? -1 : 0;
                }
            });
            
            displayTable();
        });
    }
});

function switchView(view) {
    currentView = view;
    
    if (view === 'card') {
        document.getElementById('cardView').className = '';
        document.getElementById('tableView').className = 'hidden';
        document.getElementById('cardViewBtn').classList.add('active');
        document.getElementById('tableViewBtn').classList.remove('active');
    } else {
        document.getElementById('cardView').className = 'hidden';
        document.getElementById('tableView').className = '';
        document.getElementById('cardViewBtn').classList.remove('active');
        document.getElementById('tableViewBtn').classList.add('active');
        displayTable();
    }
}
function doFilter() {
    if (selectedStrategies.length === 0) {
        alert('請至少選擇一個策略');
        return;
    }
    
    var logicMode = 'or';
    var radios = document.getElementsByName('logicMode');
    for (var i = 0; i < radios.length; i++) {
        if (radios[i].checked) {
            logicMode = radios[i].value;
            break;
        }
    }
    
    var minDiv = parseFloat(document.getElementById('minDiv').value) || 5;
    var maxPE = parseFloat(document.getElementById('maxPE').value) || 20;
    var maxK = parseFloat(document.getElementById('maxK').value) || 20;
    var maxRSI = parseFloat(document.getElementById('maxRSI').value) || 30;
    
    var usePrice = document.getElementById('usePrice').checked;
    var minPrice = parseFloat(document.getElementById('minPrice').value) || 10;
    var maxPrice = parseFloat(document.getElementById('maxPrice').value) || 300;
    
    var useCap = document.getElementById('useCap').checked;
    var minCap = parseFloat(document.getElementById('minCap').value) || 10;
    var maxCap = parseFloat(document.getElementById('maxCap').value) || 1000;
    
    var useVolume = document.getElementById('useVolume').checked;
    var minVolume = parseFloat(document.getElementById('minVolume').value) || 1.5;
    
    var useDividend = document.getElementById('useDividend').checked;
    var globalMinDiv = parseFloat(document.getElementById('globalMinDiv').value) || 3.5;
    
    var usePE = document.getElementById('usePE').checked;
    var globalMaxPE = parseFloat(document.getElementById('globalMaxPE').value) || 20;
    
    var useRSI = document.getElementById('useRSI').checked;
    var globalMaxRSI = parseFloat(document.getElementById('globalMaxRSI').value) || 91;
    
    var useK = document.getElementById('useK').checked;
    var globalMinK = parseFloat(document.getElementById('globalMinK').value) || 0;
    var globalMaxK = parseFloat(document.getElementById('globalMaxK').value) || 100;
    
    var useEPS = document.getElementById('useEPS').checked;
    var globalMinEPS = parseFloat(document.getElementById('globalMinEPS').value) || 1;
    
    filteredData = [];
    
    for (var i = 0; i < stockData.length; i++) {
        var s = stockData[i];
        var matchCount = 0;
        
        for (var j = 0; j < selectedStrategies.length; j++) {
            var strategy = selectedStrategies[j];
            var strategyMatch = false;
            
            if (strategy === 'dividend' && s.殖利率 && s.殖利率 >= minDiv) strategyMatch = true;
            if (strategy === 'value' && s.殖利率 >= minDiv && s.本益比 && s.本益比 <= maxPE) strategyMatch = true;
            if (strategy === 'kd_golden' && s.KD狀態 && (s.KD狀態.indexOf('黃金交叉') >= 0 || s.KD狀態.indexOf('K>D') >= 0)) strategyMatch = true;
            if (strategy === 'bb_upper' && s.BB位置 && s.BB位置 >= 70) strategyMatch = true;
            if (strategy === 'macd_golden' && s.MACD狀態 && (s.MACD狀態.indexOf('黃金交叉') >= 0 || s.MACD狀態.indexOf('DIF>MACD') >= 0)) strategyMatch = true;
            if (strategy === 'kd_oversold' && s.K值 < maxK && s.D值 < maxK) strategyMatch = true;
            if (strategy === 'rsi_oversold' && s.RSI && s.RSI < maxRSI) strategyMatch = true;
            if (strategy === 'bb_lower' && s.BB位置 && s.BB位置 <= 30) strategyMatch = true;
            
            if (strategyMatch) matchCount++;
        }
        
        var passFilter = false;
        if (logicMode === 'or') {
            passFilter = matchCount > 0;
        } else {
            passFilter = matchCount === selectedStrategies.length;
        }
        
        if (!passFilter) continue;
        
        if (usePrice && (s.收盤價 < minPrice || s.收盤價 > maxPrice)) continue;
        if (useCap && s.市值億 && (s.市值億 < minCap || s.市值億 > maxCap)) continue;
        if (useVolume && (!s.量比 || s.量比 < minVolume)) continue;
        if (useDividend && (!s.殖利率 || s.殖利率 < globalMinDiv)) continue;
        if (usePE && s.本益比 && s.本益比 > globalMaxPE) continue;
        if (useRSI && s.RSI && s.RSI > globalMaxRSI) continue;
        if (useK && s.K值 && (s.K值 < globalMinK || s.K值 > globalMaxK)) continue;
        if (useEPS && (!s.EPS || s.EPS < globalMinEPS)) continue;
        
        filteredData.push(s);
    }
    
    document.getElementById('count').textContent = filteredData.length;
    
    if (currentView === 'card') {
        displayCards();
    } else {
        displayTable();
    }
    
    document.getElementById('results').className = '';
    setTimeout(function() {
        document.getElementById('results').scrollIntoView({behavior: 'smooth'});
    }, 100);
}

function displayCards() {
    var html = '';
    
    for (var i = 0; i < filteredData.length; i++) {
        var s = filteredData[i];
        html += '<div class="stock-item">';
        html += '<div class="stock-header">';
        html += '<div><div class="stock-code">' + s.股票代號 + ' ' + s.股票名稱 + '</div></div>';
        html += '<div class="stock-price">$' + s.收盤價 + '</div>';
        html += '</div>';
        html += '<div class="stock-details">';
        html += '<div>K: ' + (s.K值 ? s.K值.toFixed(1) : 'N/A') + '</div>';
        html += '<div>D: ' + (s.D值 ? s.D值.toFixed(1) : 'N/A') + '</div>';
        html += '<div>RSI: ' + (s.RSI ? s.RSI.toFixed(1) : 'N/A') + '</div>';
        html += '<div>BB: ' + (s.BB位置 ? s.BB位置.toFixed(1) + '%' : 'N/A') + '</div>';
        html += '<div>殖利率: ' + (s.殖利率 ? s.殖利率.toFixed(2) + '%' : 'N/A') + '</div>';
        html += '<div>本益比: ' + (s.本益比 ? s.本益比.toFixed(1) : 'N/A') + '</div>';
        html += '<div>EPS: ' + (s.EPS ? s.EPS.toFixed(2) : 'N/A') + '</div>';
        html += '<div>市值: ' + (s.市值億 ? s.市值億.toFixed(1) + '億' : 'N/A') + '</div>';
        html += '<div>量比: ' + (s.量比 ? s.量比.toFixed(2) : 'N/A') + '</div>';
        html += '</div></div>';
    }
    
    if (html === '') {
        html = '<div style="text-align:center;padding:40px;color:#999">😔 沒有符合條件的股票</div>';
    }
    
    document.getElementById('list').innerHTML = html;
}

function displayTable() {
    var headers = document.querySelectorAll('.stock-table th.sortable');
    for (var i = 0; i < headers.length; i++) {
        headers[i].className = 'sortable';
    }
    
    if (sortColumn) {
        var sortedHeader = document.querySelector('.stock-table th[data-col="' + sortColumn + '"]');
        if (sortedHeader) {
            sortedHeader.className = 'sortable sorted-' + sortDirection;
        }
    }
    
    var html = '';
    
    for (var i = 0; i < filteredData.length; i++) {
        var s = filteredData[i];
        html += '<tr>';
        html += '<td>' + s.股票代號 + '</td>';
        html += '<td>' + s.股票名稱 + '</td>';
        html += '<td>' + s.收盤價 + '</td>';
        html += '<td>' + (s.K值 ? s.K值.toFixed(1) : '') + '</td>';
        html += '<td>' + (s.D值 ? s.D值.toFixed(1) : '') + '</td>';
        html += '<td>' + (s.RSI ? s.RSI.toFixed(1) : '') + '</td>';
        html += '<td>' + (s.BB位置 ? s.BB位置.toFixed(1) : '') + '</td>';
        html += '<td>' + (s.成交量張 || '') + '</td>';
        html += '<td>' + (s.量比 ? s.量比.toFixed(2) : '') + '</td>';
        html += '<td>' + (s.殖利率 ? s.殖利率.toFixed(2) : '') + '</td>';
        html += '<td>' + (s.本益比 ? s.本益比.toFixed(1) : '') + '</td>';
        html += '<td>' + (s.EPS ? s.EPS.toFixed(2) : '') + '</td>';
        html += '<td>' + (s.市值億 ? s.市值億.toFixed(1) : '') + '</td>';
        html += '</tr>';
    }
    
    if (html === '') {
        html = '<tr><td colspan="13" style="text-align:center;padding:40px;color:#999">😔 沒有符合條件的股票</td></tr>';
    }
    
    document.getElementById('tableBody').innerHTML = html;
}

function exportCSV() {
    var csv = '\\uFEFF股票代號,股票名稱,收盤價,K值,D值,RSI,BB位置,成交量張,量比,殖利率,本益比,EPS,市值億\\n';
    
    for (var i = 0; i < filteredData.length; i++) {
        var s = filteredData[i];
        csv += s.股票代號 + ',' + s.股票名稱 + ',' + s.收盤價 + ',';
        csv += (s.K值 ? s.K值.toFixed(2) : '') + ',';
        csv += (s.D值 ? s.D值.toFixed(2) : '') + ',';
        csv += (s.RSI ? s.RSI.toFixed(2) : '') + ',';
        csv += (s.BB位置 ? s.BB位置.toFixed(1) : '') + ',';
        csv += (s.成交量張 ? s.成交量張 : '') + ',';
        csv += (s.量比 ? s.量比.toFixed(2) : '') + ',';
        csv += (s.殖利率 ? s.殖利率.toFixed(2) : '') + ',';
        csv += (s.本益比 ? s.本益比.toFixed(2) : '') + ',';
        csv += (s.EPS ? s.EPS.toFixed(2) : '') + ',';
        csv += (s.市值億 ? s.市值億.toFixed(2) : '') + '\\n';
    }
    
    var blob = new Blob([csv], {type: 'text/csv;charset=utf-8'});
    var link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = '篩選結果.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}
</script>
</body>
</html>
'''
# 取得更新時間
update_time = df['更新時間'].iloc[0] if '更新時間' in df.columns and len(df) > 0 else datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 依序替換
html_content = html_template.replace('UPDATETIME', update_time)
html_content = html_content.replace('TOTALCOUNT', str(len(df)))
html_content = html_content.replace('DATAPLACEHOLDER', json_data)

# 儲存檔案
output_file = "stock_filter_latest.html"

with open(output_file, 'w', encoding='utf-8') as f:
    f.write(html_content)

file_size = len(html_content)
print(f"✅ 打包完成！")
print(f"   檔案：{output_file}")
print(f"   大小：{file_size:,} bytes ({file_size/1024:.1f} KB)")
print()
print("=" * 70)
print("📱 新功能：全局參數篩選")
print("  ✅ 殖利率篩選（全局）")
print("  ✅ 本益比上限（全局）")
print("  ✅ RSI上限（全局）")
print("  ✅ K值範圍（全局）")
print("  ✅ EPS篩選（全局）")
print()
print("💡 使用方式：")
print("  策略：選擇你要的策略（不用全選）")
print("  全局篩選：勾選需要的額外條件")
print("  → 像電腦版策略11一樣自由組合！")
print("=" * 70)
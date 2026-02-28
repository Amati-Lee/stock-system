"""
create_trend_mobile.py
生成手機版趨勢篩選器（含歷史比對功能）
"""
import pandas as pd
import json
from datetime import datetime
import glob

def get_recent_files(days=2):
    """取得最近 N 天的數據檔案"""
    files = glob.glob("stock_data_*.csv")
    if len(files) < days:
        return None
    files_sorted = sorted(files, reverse=True)
    return files_sorted[:days]

print("=" * 70)
print("  打包趨勢篩選器為手機版")
print("=" * 70)
print()

# 取得今天和昨天的數據
files = get_recent_files(2)

if not files or len(files) < 2:
    print("❌ 需要至少 2 天的數據")
    print("   請先執行：python test_trend.py")
    exit(1)

today_file = files[0]
yesterday_file = files[1]

print(f"📊 今天數據：{today_file}")
print(f"📊 昨天數據：{yesterday_file}")
print()

# 載入數據
df_today = pd.read_csv(today_file, encoding="utf-8-sig")
df_yesterday = pd.read_csv(yesterday_file, encoding="utf-8-sig")

print(f"✅ 今天：{len(df_today)} 筆")
print(f"✅ 昨天：{len(df_yesterday)} 筆")

# 合併數據
df_merged = pd.merge(
    df_today, 
    df_yesterday, 
    on='股票代號', 
    suffixes=('_今', '_昨'),
    how='inner'
)

print(f"🔗 成功比對：{len(df_merged)} 筆")
print()

# 計算變化
df_merged['漲跌幅'] = ((df_merged['收盤價_今'] - df_merged['收盤價_昨']) / df_merged['收盤價_昨'] * 100).round(2)
df_merged['K值變化'] = (df_merged['K值_今'] - df_merged['K值_昨']).round(2)
df_merged['D值變化'] = (df_merged['D值_今'] - df_merged['D值_昨']).round(2)
df_merged['RSI變化'] = (df_merged['RSI_今'] - df_merged['RSI_昨']).round(2)
df_merged['BB變化'] = (df_merged['BB位置_今'] - df_merged['BB位置_昨']).round(2)
df_merged['量比變化'] = (df_merged['量比_今'] - df_merged['量比_昨']).round(2)

# 選擇輸出欄位
output_cols = [
    '股票代號', '股票名稱_今', '收盤價_今', '漲跌幅',
    'K值_今', 'K值變化', 'D值_今', 'D值變化',
    'RSI_今', 'RSI變化', 'BB位置_今', 'BB變化',
    '量比_今', '量比變化', '殖利率_今', '本益比_今', '市值億_今'
]

df_output = df_merged[output_cols].copy()
df_output.columns = [
    '股票代號', '股票名稱', '收盤價', '漲跌幅',
    'K值', 'K變化', 'D值', 'D變化',
    'RSI', 'RSI變化', 'BB位置', 'BB變化',
    '量比', '量比變化', '殖利率', '本益比', '市值億'
]

# 轉 JSON
json_data = df_output.to_json(orient='records', force_ascii=False)

print(f"📊 數據大小：{len(json_data)/1024:.1f} KB")
print()

# HTML 模板
html_template = '''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>趨勢篩選器</title>
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
.change-up {color:#e74c3c;font-weight:bold}
.change-down {color:#27ae60;font-weight:bold}
.hidden {display:none}
.divider {height:1px;background:#e0e0e0;margin:15px 0}
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
</style>
</head>
<body>
<div class="container">
<div class="card">
<h1>📈 趨勢篩選器</h1>
<div class="info">比對：COMPAREDATE | 總筆數：TOTALCOUNT</div>
</div>

<div class="card">
<div class="section-title">📊 趨勢策略（可複選）</div>

<div style="margin-bottom:10px;font-size:14px;color:#666">價格趨勢</div>
<div class="btn" data-strategy="price_up">連續上漲</div>
<div class="btn" data-strategy="price_down">連續下跌</div>

<div style="margin-bottom:10px;margin-top:15px;font-size:14px;color:#666">技術指標轉強</div>
<div class="btn" data-strategy="kd_strong">KD轉強</div>
<div class="btn" data-strategy="rsi_strong">RSI轉強</div>
<div class="btn" data-strategy="bb_up">BB上升</div>

<div style="margin-bottom:10px;margin-top:15px;font-size:14px;color:#666">技術指標轉弱</div>
<div class="btn" data-strategy="kd_weak">KD轉弱</div>
<div class="btn" data-strategy="rsi_weak">RSI轉弱</div>
<div class="btn" data-strategy="bb_down">BB下降</div>

<div style="margin-bottom:10px;margin-top:15px;font-size:14px;color:#666">量能變化</div>
<div class="btn" data-strategy="volume_up">量能放大</div>
<div class="btn" data-strategy="volume_down">量能縮小</div>

<div id="params" class="hidden">
<div class="divider"></div>

<div class="section-title">⚙️ 篩選參數</div>

<div class="input-row">
<div class="input-group">
<label>漲跌幅門檻（%）</label>
<input type="number" id="priceChange" value="1" step="0.5">
</div>
<div class="input-group">
<label>指標變化門檻</label>
<input type="number" id="indChange" value="3" step="1">
</div>
</div>

<div class="input-row">
<div class="input-group">
<label>量比變化門檻</label>
<input type="number" id="volChange" value="0.5" step="0.1">
</div>
<div class="input-group">
<label>最低K值</label>
<input type="number" id="minK" value="0" step="5">
</div>
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
<th class="sortable" data-col="漲跌幅">漲跌%</th>
<th class="sortable" data-col="K值">K值</th>
<th class="sortable" data-col="K變化">K變化</th>
<th class="sortable" data-col="D值">D值</th>
<th class="sortable" data-col="D變化">D變化</th>
<th class="sortable" data-col="RSI">RSI</th>
<th class="sortable" data-col="RSI變化">RSI變化</th>
<th class="sortable" data-col="量比">量比</th>
<th class="sortable" data-col="量比變化">量比變化</th>
<th class="sortable" data-col="殖利率">殖利率</th>
<th class="sortable" data-col="本益比">本益比</th>
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
    
    var priceChange = parseFloat(document.getElementById('priceChange').value) || 1;
    var indChange = parseFloat(document.getElementById('indChange').value) || 3;
    var volChange = parseFloat(document.getElementById('volChange').value) || 0.5;
    var minK = parseFloat(document.getElementById('minK').value) || 0;
    
    filteredData = [];
    
    for (var i = 0; i < stockData.length; i++) {
        var s = stockData[i];
        var matchCount = 0;
        
        for (var j = 0; j < selectedStrategies.length; j++) {
            var strategy = selectedStrategies[j];
            var strategyMatch = false;
            
            if (strategy === 'price_up' && s.漲跌幅 >= priceChange) strategyMatch = true;
            if (strategy === 'price_down' && s.漲跌幅 <= -priceChange) strategyMatch = true;
            if (strategy === 'kd_strong' && s.K變化 >= indChange && s.D變化 >= indChange) strategyMatch = true;
            if (strategy === 'rsi_strong' && s.RSI變化 >= indChange) strategyMatch = true;
            if (strategy === 'bb_up' && s.BB變化 >= indChange) strategyMatch = true;
            if (strategy === 'kd_weak' && s.K變化 <= -indChange && s.D變化 <= -indChange) strategyMatch = true;
            if (strategy === 'rsi_weak' && s.RSI變化 <= -indChange) strategyMatch = true;
            if (strategy === 'bb_down' && s.BB變化 <= -indChange) strategyMatch = true;
            if (strategy === 'volume_up' && s.量比變化 >= volChange) strategyMatch = true;
            if (strategy === 'volume_down' && s.量比變化 <= -volChange) strategyMatch = true;
            
            if (strategyMatch) matchCount++;
        }
        
        if (matchCount === selectedStrategies.length && s.K值 >= minK) {
            filteredData.push(s);
        }
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
        var priceClass = s.漲跌幅 >= 0 ? 'change-up' : 'change-down';
        var priceSymbol = s.漲跌幅 >= 0 ? '+' : '';
        
        html += '<div class="stock-item">';
        html += '<div class="stock-header">';
        html += '<div><div class="stock-code">' + s.股票代號 + ' ' + s.股票名稱 + '</div></div>';
        html += '<div class="stock-price">$' + s.收盤價 + '</div>';
        html += '</div>';
        html += '<div class="stock-details">';
        html += '<div class="' + priceClass + '">漲跌: ' + priceSymbol + s.漲跌幅.toFixed(2) + '%</div>';
        html += '<div>K: ' + (s.K值 ? s.K值.toFixed(1) : 'N/A') + ' (' + (s.K變化 >= 0 ? '+' : '') + (s.K變化 ? s.K變化.toFixed(1) : '0') + ')</div>';
        html += '<div>D: ' + (s.D值 ? s.D值.toFixed(1) : 'N/A') + ' (' + (s.D變化 >= 0 ? '+' : '') + (s.D變化 ? s.D變化.toFixed(1) : '0') + ')</div>';
        html += '<div>RSI: ' + (s.RSI ? s.RSI.toFixed(1) : 'N/A') + ' (' + (s.RSI變化 >= 0 ? '+' : '') + (s.RSI變化 ? s.RSI變化.toFixed(1) : '0') + ')</div>';
        html += '<div>BB: ' + (s.BB位置 ? s.BB位置.toFixed(1) : 'N/A') + ' (' + (s.BB變化 >= 0 ? '+' : '') + (s.BB變化 ? s.BB變化.toFixed(1) : '0') + ')</div>';
        html += '<div>量比: ' + (s.量比 ? s.量比.toFixed(2) : 'N/A') + ' (' + (s.量比變化 >= 0 ? '+' : '') + (s.量比變化 ? s.量比變化.toFixed(2) : '0') + ')</div>';
        html += '<div>殖利率: ' + (s.殖利率 ? s.殖利率.toFixed(2) + '%' : 'N/A') + '</div>';
        html += '<div>本益比: ' + (s.本益比 ? s.本益比.toFixed(1) : 'N/A') + '</div>';
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
        html += '<td class="' + (s.漲跌幅 >= 0 ? 'change-up' : 'change-down') + '">' + (s.漲跌幅 >= 0 ? '+' : '') + s.漲跌幅.toFixed(2) + '%</td>';
        html += '<td>' + (s.K值 ? s.K值.toFixed(1) : '') + '</td>';
        html += '<td class="' + (s.K變化 >= 0 ? 'change-up' : 'change-down') + '">' + (s.K變化 >= 0 ? '+' : '') + (s.K變化 ? s.K變化.toFixed(1) : '0') + '</td>';
        html += '<td>' + (s.D值 ? s.D值.toFixed(1) : '') + '</td>';
        html += '<td class="' + (s.D變化 >= 0 ? 'change-up' : 'change-down') + '">' + (s.D變化 >= 0 ? '+' : '') + (s.D變化 ? s.D變化.toFixed(1) : '0') + '</td>';
        html += '<td>' + (s.RSI ? s.RSI.toFixed(1) : '') + '</td>';
        html += '<td class="' + (s.RSI變化 >= 0 ? 'change-up' : 'change-down') + '">' + (s.RSI變化 >= 0 ? '+' : '') + (s.RSI變化 ? s.RSI變化.toFixed(1) : '0') + '</td>';
        html += '<td>' + (s.量比 ? s.量比.toFixed(2) : '') + '</td>';
        html += '<td class="' + (s.量比變化 >= 0 ? 'change-up' : 'change-down') + '">' + (s.量比變化 >= 0 ? '+' : '') + (s.量比變化 ? s.量比變化.toFixed(2) : '0') + '</td>';
        html += '<td>' + (s.殖利率 ? s.殖利率.toFixed(2) : '') + '</td>';
        html += '<td>' + (s.本益比 ? s.本益比.toFixed(1) : '') + '</td>';
        html += '</tr>';
    }
    
    if (html === '') {
        html = '<tr><td colspan="14" style="text-align:center;padding:40px;color:#999">😔 沒有符合條件的股票</td></tr>';
    }
    
    document.getElementById('tableBody').innerHTML = html;
}

function exportCSV() {
    var csv = '\\uFEFF股票代號,股票名稱,收盤價,漲跌幅%,K值,K變化,D值,D變化,RSI,RSI變化,量比,量比變化,殖利率,本益比\\n';
    
    for (var i = 0; i < filteredData.length; i++) {
        var s = filteredData[i];
        csv += s.股票代號 + ',' + s.股票名稱 + ',' + s.收盤價 + ',';
        csv += (s.漲跌幅 ? s.漲跌幅.toFixed(2) : '') + ',';
        csv += (s.K值 ? s.K值.toFixed(2) : '') + ',';
        csv += (s.K變化 ? s.K變化.toFixed(2) : '') + ',';
        csv += (s.D值 ? s.D值.toFixed(2) : '') + ',';
        csv += (s.D變化 ? s.D變化.toFixed(2) : '') + ',';
        csv += (s.RSI ? s.RSI.toFixed(2) : '') + ',';
        csv += (s.RSI變化 ? s.RSI變化.toFixed(2) : '') + ',';
        csv += (s.量比 ? s.量比.toFixed(2) : '') + ',';
        csv += (s.量比變化 ? s.量比變化.toFixed(2) : '') + ',';
        csv += (s.殖利率 ? s.殖利率.toFixed(2) : '') + ',';
        csv += (s.本益比 ? s.本益比.toFixed(2) : '') + '\\n';
    }
    
    var blob = new Blob([csv], {type: 'text/csv;charset=utf-8'});
    var link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = '趨勢篩選結果.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}
</script>
</body>
</html>
'''

# 替換數據
compare_date = f"{today_file.split('_')[-1].replace('.csv','')} vs {yesterday_file.split('_')[-1].replace('.csv','')}"
html_content = html_template.replace('COMPAREDATE', compare_date)
html_content = html_content.replace('TOTALCOUNT', str(len(df_output)))
html_content = html_content.replace('DATAPLACEHOLDER', json_data)

# 儲存
output_file = "stock_trend_latest.html"

with open(output_file, 'w', encoding='utf-8') as f:
    f.write(html_content)

file_size = len(html_content)
print(f"✅ 趨勢篩選器打包完成！")
print(f"   檔案：{output_file}")
print(f"   大小：{file_size:,} bytes ({file_size/1024:.1f} KB)")
print()
print("=" * 70)
print("📱 功能：")
print("  ✅ 10 種趨勢策略")
print("  ✅ 價格/技術/量能趨勢")
print("  ✅ 顯示變化數值（+/- 標示）")
print("  ✅ 卡片/表格檢視")
print("  ✅ CSV 匯出")
print()
print("💡 使用方式：")
print("  1. 傳到手機")
print("  2. 選擇趨勢策略")
print("  3. 調整參數門檻")
print("  4. 開始篩選")
print("=" * 70)

/**
 * 竞彩SP抓取 v5 — DOM表格提取 (零CORS)
 *
 * 用法:
 *   1. 打开 https://www.sporttery.cn/jc/jsq/zqspf/ 或 zqhhgg
 *   2. 等比赛列表加载完成 (看到表格数据)
 *   3. F12 → Console → 粘贴 → 回车
 */
(function(){
  console.clear();

  // 等1秒确保DOM渲染完成
  setTimeout(function(){
    var rows = document.querySelectorAll('table tr, .portlet, [class*="match"], [class*="odds"]');
    console.log('DOM元素: ' + rows.length + ' 个候选行');

    if (rows.length === 0) {
      // 尝试从页面内嵌JSON提取 (页面初始化数据通常在script标签或全局变量中)
      var scripts = document.querySelectorAll('script');
      for (var i = 0; i < scripts.length; i++) {
        var txt = scripts[i].textContent || scripts[i].innerHTML || '';
        if (txt.indexOf('matchList') > -1 && txt.length > 500) {
          console.log('在script['+i+']中找到数据, 长度=' + txt.length);
          try {
            // 尝试提取JSON
            var m = txt.match(/\{"matchId"[^}]*"matchResultList":\[[^\]]*\]\}/);
            if (m) { console.log('JSON片段: ' + m[0].substring(0,300)); }
          } catch(e){}
        }
      }

      // 打印页面结构帮助调试
      console.log('页面标题: ' + document.title);
      console.log('表格数量: ' + document.querySelectorAll('table').length);
      console.log('页面文本前300字: ' + (document.body?.innerText||'').substring(0,300));
      console.log('\n💡 如果页面表格为空, 请等待比赛数据加载后再粘贴');
      return;
    }

    // 提取表格数据
    var results = [];
    var allText = document.body.innerText || '';
    var lines = allText.split('\n').filter(function(l){ return l.trim().length > 5; });
    console.log('页面文本行数: ' + lines.length);

    // 尝试识别赔率格式 (数字.数字)
    var oddsPattern = /\d+\.\d{2}/g;
    var oddsMatches = allText.match(oddsPattern);
    if (oddsMatches) {
      console.log('赔率数字: ' + oddsMatches.slice(0,20).join(', '));
    }

    // 打印前20行帮助分析
    console.log('\n--- 页面文本(前30行) ---');
    for (var j = 0; j < Math.min(30, lines.length); j++) {
      console.log(j + ': ' + lines[j]);
    }

    console.log('\n💡 请将上面输出贴给我, 我根据页面结构调整提取逻辑');
  }, 2000);
})();

const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // 收集所有的请求
  const requests = [];
  page.on('request', request => {
    requests.push({
      url: request.url(),
      method: request.method(),
      headers: request.headers(),
      postData: request.postData()
    });
    console.log(`→ ${request.method()} ${request.url()}`);
  });

  // 收集所有的响应
  const responses = [];
  page.on('response', response => {
    responses.push({
      url: response.url(),
      status: response.status(),
      statusText: response.statusText()
    });
    console.log(`← ${response.status()} ${response.url()}`);
  });

  // 收集控制台消息
  const consoleLogs = [];
  page.on('console', msg => {
    const logEntry = {
      type: msg.type(),
      text: msg.text(),
      location: msg.location()
    };
    consoleLogs.push(logEntry);
    console.log(`[${msg.type().toUpperCase()}] ${msg.text()}`);
  });

  // 收集页面错误
  const pageErrors = [];
  page.on('pageerror', error => {
    pageErrors.push({
      message: error.message,
      stack: error.stack
    });
    console.error(`[PAGE ERROR] ${error.message}`);
  });

  try {
    console.log('\n=== 开始访问页面 ===\n');
    await page.goto('http://localhost:1313/posts/7/', {
      waitUntil: 'networkidle',
      timeout: 30000
    });

    // 等待一段时间让 Giscus 加载
    await page.waitForTimeout(5000);

    console.log('\n=== 检查 Giscus 脚本标签 ===\n');
    const giscusScript = await page.$('script[src*="giscus"]');
    if (giscusScript) {
      const scriptSrc = await giscusScript.getAttribute('src');
      console.log('✓ 找到 Giscus 脚本:', scriptSrc);

      const attributes = await giscusScript.evaluate(el => {
        return {
          'data-repo': el.getAttribute('data-repo'),
          'data-repo-id': el.getAttribute('data-repo-id'),
          'data-category': el.getAttribute('data-category'),
          'data-category-id': el.getAttribute('data-category-id'),
          'data-mapping': el.getAttribute('data-mapping'),
          'data-strict': el.getAttribute('data-strict'),
          'data-reactions-enabled': el.getAttribute('data-reactions-enabled'),
          'data-emit-metadata': el.getAttribute('data-emit-metadata'),
          'data-input-position': el.getAttribute('data-input-position'),
          'data-theme': el.getAttribute('data-theme'),
          'data-lang': el.getAttribute('data-lang'),
          'crossorigin': el.getAttribute('crossorigin')
        };
      });

      console.log('\nGiscus 属性配置:');
      for (const [key, value] of Object.entries(attributes)) {
        console.log(`  ${key}: ${value}`);
      }
    } else {
      console.log('✗ 未找到 Giscus 脚本标签');
    }

    console.log('\n=== 检查 Giscus iframe ===\n');
    const giscusIframe = await page.$('iframe.giscus-frame');
    if (giscusIframe) {
      const iframeSrc = await giscusIframe.getAttribute('src');
      console.log('✓ 找到 Giscus iframe');
      console.log('iframe src:', iframeSrc);
      console.log('iframe src 长度:', iframeSrc ? iframeSrc.length : 0);

      if (iframeSrc && iframeSrc.length > 2000) {
        console.log('⚠️  警告: iframe src URL 过长 (>' + iframeSrc.length + ' 字符)');
        console.log('这可能导致 URI_TOO_LONG 错误');
      }
    } else {
      console.log('✗ 未找到 Giscus iframe');
    }

    console.log('\n=== Giscus 相关的网络请求 ===\n');
    const giscusRequests = requests.filter(r => r.url.includes('giscus'));
    if (giscusRequests.length > 0) {
      giscusRequests.forEach((req, idx) => {
        console.log(`\n请求 #${idx + 1}:`);
        console.log(`  Method: ${req.method}`);
        console.log(`  URL: ${req.url}`);
        console.log(`  URL 长度: ${req.url.length} 字符`);
        if (req.url.length > 2000) {
          console.log(`  ⚠️  URL 过长!`);
        }
      });
    } else {
      console.log('未找到 Giscus 相关的网络请求');
    }

    console.log('\n=== Giscus 相关的响应 ===\n');
    const giscusResponses = responses.filter(r => r.url.includes('giscus'));
    if (giscusResponses.length > 0) {
      giscusResponses.forEach((res, idx) => {
        console.log(`\n响应 #${idx + 1}:`);
        console.log(`  Status: ${res.status} ${res.statusText}`);
        console.log(`  URL: ${res.url}`);
        if (res.status >= 400) {
          console.log(`  ⚠️  请求失败!`);
        }
      });
    } else {
      console.log('未找到 Giscus 相关的响应');
    }

    console.log('\n=== 页面 HTML 中的 Giscus 部分 ===\n');
    const giscusContainer = await page.$('.giscus');
    if (giscusContainer) {
      const giscusHTML = await giscusContainer.innerHTML();
      console.log(giscusHTML.substring(0, 1000));
      if (giscusHTML.length > 1000) {
        console.log(`\n... (总共 ${giscusHTML.length} 字符)`);
      }
    } else {
      console.log('未找到 .giscus 容器');
    }

    console.log('\n=== 控制台错误 ===\n');
    const errors = consoleLogs.filter(log => log.type === 'error');
    if (errors.length > 0) {
      errors.forEach((err, idx) => {
        console.log(`\n错误 #${idx + 1}:`);
        console.log(`  ${err.text}`);
      });
    } else {
      console.log('无控制台错误');
    }

    console.log('\n=== 页面错误 ===\n');
    if (pageErrors.length > 0) {
      pageErrors.forEach((err, idx) => {
        console.log(`\n错误 #${idx + 1}:`);
        console.log(`  ${err.message}`);
        if (err.stack) {
          console.log(`  Stack: ${err.stack}`);
        }
      });
    } else {
      console.log('无页面错误');
    }

    // 生成详细报告文件
    const report = {
      timestamp: new Date().toISOString(),
      url: 'http://localhost:1313/posts/7/',
      giscusScript: giscusScript ? 'found' : 'not found',
      giscusIframe: giscusIframe ? 'found' : 'not found',
      requests: giscusRequests,
      responses: giscusResponses,
      consoleLogs: consoleLogs,
      pageErrors: pageErrors
    };

    const fs = require('fs');
    fs.writeFileSync(
      '/Users/nio/ddnio.github.io/giscus-diagnostic-report.json',
      JSON.stringify(report, null, 2)
    );
    console.log('\n=== 详细报告已保存到 giscus-diagnostic-report.json ===\n');

    // 截图
    await page.screenshot({
      path: '/Users/nio/ddnio.github.io/giscus-screenshot.png',
      fullPage: true
    });
    console.log('页面截图已保存到 giscus-screenshot.png\n');

  } catch (error) {
    console.error('执行过程中出错:', error);
  } finally {
    await browser.close();
  }
})();

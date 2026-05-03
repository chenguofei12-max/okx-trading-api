/**
 * OKX API 反向代理 - Vercel Serverless Function
 * 
 * 支持两种调用方式：
 * 1. 路径方式：/api/v5/account/balance（推荐）
 * 2. 参数方式：/api/proxy?path=/api/v5/account/balance（兼容）
 */

const OKX_API_HOST = 'https://www.okx.com';

export default async function handler(req, res) {
  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, PUT, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', '*');
    return res.status(204).send('');
  }

  const { path, ...queryParams } = req.query;
  let targetPath;
  
  if (path && path.startsWith('/api/')) {
    targetPath = path;
  } else if (req.url.startsWith('/api/v5/')) {
    const urlObj = new URL(req.url, 'http://localhost');
    targetPath = urlObj.pathname;
  } else {
    return res.status(400).json({
      code: '400',
      msg: 'Use /api/v5/... or /api/proxy?path=/api/v5/...'
    });
  }

  const queryString = Object.entries(queryParams)
    .filter(([key]) => key !== 'path')
    .map(([key, value]) => `${key}=${value}`)
    .join('&');

  if (queryString) targetPath += `?${queryString}`;

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Expose-Headers', '*');

  try {
    const headers = {};
    Object.keys(req.headers).forEach(key => {
      if (!['host', 'connection', 'content-length'].includes(key.toLowerCase())) {
        headers[key] = req.headers[key];
      }
    });

    const fetchOptions = { method: req.method, headers };

    if (req.method !== 'GET' && req.body) {
      fetchOptions.body = typeof req.body === 'string' ? req.body : JSON.stringify(req.body);
    }

    const targetUrl = `${OKX_API_HOST}${targetPath}`;
    console.log(`[Proxy] ${req.method} ${targetUrl}`);
    const response = await fetch(targetUrl, fetchOptions);
    const responseBody = await response.text();

    response.headers.forEach((value, key) => {
      if (!['transfer-encoding', 'content-encoding', 'content-length'].includes(key.toLowerCase())) {
        res.setHeader(key, value);
      }
    });

    res.status(response.status).send(responseBody);

  } catch (error) {
    console.error(`[Proxy] Error: ${error.message}`);
    res.status(500).json({
      code: '500',
      msg: `Proxy error: ${error.message}`
    });
  }
}

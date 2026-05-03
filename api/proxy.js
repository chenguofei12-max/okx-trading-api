/**
 * OKX API 反向代理 - Vercel Serverless Function
 * 部署后：https://xxx.vercel.app/api/proxy?path=/api/v5/...
 */

const OKX_API_HOST = 'www.okx.com';

export default async function handler(req, res) {
  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, PUT, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', '*');
    return res.status(204).send('');
  }

  const { path, ...queryParams } = req.query;
  
  if (!path || !path.startsWith('/api/')) {
    return res.status(400).json({
      code: '400',
      msg: 'Missing or invalid path parameter. Use ?path=/api/v5/...'
    });
  }

  const queryString = Object.entries(queryParams)
    .filter(([key]) => key !== 'path')
    .map(([key, value]) => `${key}=${value}`)
    .join('&');
  
  const targetPath = path + (queryString ? `?${queryString}` : '');

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

    const targetUrl = `https://${OKX_API_HOST}${targetPath}`;
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

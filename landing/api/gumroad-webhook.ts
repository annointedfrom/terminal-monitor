import type { VercelRequest, VercelResponse } from '@vercel/node'
import jwt from 'jsonwebtoken'
import { Resend } from 'resend'

const PERMALINK_TO_TIER: Record<string, string> = {
  anilts: 'base',
  cwtip: 'mid',
  lgubie: 'diamond',
}

const TIER_LABEL: Record<string, string> = {
  base: 'Base',
  mid: 'Mid',
  diamond: 'Diamond',
}

const TIER_FEATURES: Record<string, string[]> = {
  base: [
    'Port scanner + process monitor',
    'MCP server detection',
    'CPU / RAM / GPU graphs',
    'Shell history viewer',
    'Configurable alerts',
  ],
  mid: [
    'Everything in Base',
    'Memory server (SQLite)',
    'Plugin architecture',
    'Update notifications',
  ],
  diamond: [
    'Everything in Mid',
    'NeuroLinked brain sync (every 60s)',
    'Memory insights dashboard',
    'Priority support',
  ],
}

const EXP_2099 = Math.floor(new Date('2099-01-01T00:00:00Z').getTime() / 1000)

function keyEmail(email: string, tier: string, licenseKey: string): string {
  const label = TIER_LABEL[tier]
  const features = TIER_FEATURES[tier].map(f => `<li style="margin:4px 0;">${f}</li>`).join('')
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0d0d0d;font-family:'Courier New',Courier,monospace;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d0d;padding:40px 20px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#0a0e0a;border:1px solid rgba(0,255,100,0.25);border-radius:6px;overflow:hidden;max-width:600px;width:100%;">
  <tr><td style="background:#0a0e0a;border-bottom:1px solid rgba(0,255,100,0.15);padding:28px 36px;">
    <span style="color:#00ff64;font-size:11px;letter-spacing:3px;text-transform:uppercase;">Terminal Monitor</span>
    <h1 style="margin:10px 0 0;color:#f9fafb;font-size:20px;font-weight:700;">Your ${label} license key is ready</h1>
  </td></tr>
  <tr><td style="padding:32px 36px;color:#e5e7eb;font-size:14px;line-height:1.7;">
    <p style="margin:0 0 20px;">Thanks for buying Terminal Monitor ${label}. Paste this key into the setup wizard when you first launch the dashboard.</p>
    <div style="background:#0d1a0d;border:1px solid rgba(0,255,100,0.4);border-radius:4px;padding:20px 24px;margin:0 0 28px;">
      <div style="color:#00ff64;font-size:10px;letter-spacing:2px;margin-bottom:10px;">LICENSE KEY</div>
      <div style="color:#f9fafb;font-size:12px;word-break:break-all;line-height:1.5;">${licenseKey}</div>
    </div>
    <p style="margin:0 0 8px;color:#00ff64;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;">Setup</p>
    <ol style="margin:0 0 28px;padding-left:20px;color:#d1d5db;font-size:13px;line-height:1.8;">
      <li>Download the zip from <a href="https://github.com/annointedfrom/terminal-monitor/releases/latest" style="color:#00ff64;">github.com/annointedfrom/terminal-monitor</a></li>
      <li>Extract and run: <span style="color:#00ff64;">.venv\\Scripts\\uvicorn termmon.main:app --port 8084</span></li>
      <li>Open <span style="color:#00ff64;">http://localhost:8084</span> — the setup wizard will appear</li>
      <li>Paste your license key into the <strong>License Key</strong> field and save</li>
    </ol>
    <p style="margin:0 0 8px;color:#00ff64;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;">What's unlocked</p>
    <ul style="margin:0 0 28px;padding-left:20px;color:#d1d5db;font-size:13px;line-height:1.8;">${features}</ul>
    <p style="margin:0;color:#9ca3af;font-size:13px;">Questions? Reply to this email — I respond within 24h.<br>— Angel Vaquera Jr.</p>
  </td></tr>
  <tr><td style="border-top:1px solid rgba(0,255,100,0.1);padding:18px 36px;">
    <p style="margin:0;color:#4b5563;font-size:11px;">Terminal Monitor · <a href="https://landing-eight-rho-26.vercel.app" style="color:#4b5563;">landing-eight-rho-26.vercel.app</a></p>
  </td></tr>
</table>
</td></tr></table>
</body></html>`
}

function welcomeEmail(): string {
  const features = TIER_FEATURES['base'].map(f => `<li style="margin:4px 0;">${f}</li>`).join('')
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0d0d0d;font-family:'Courier New',Courier,monospace;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d0d;padding:40px 20px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#0a0e0a;border:1px solid rgba(0,255,100,0.25);border-radius:6px;overflow:hidden;max-width:600px;width:100%;">
  <tr><td style="background:#0a0e0a;border-bottom:1px solid rgba(0,255,100,0.15);padding:28px 36px;">
    <span style="color:#00ff64;font-size:11px;letter-spacing:3px;text-transform:uppercase;">Terminal Monitor</span>
    <h1 style="margin:10px 0 0;color:#f9fafb;font-size:20px;font-weight:700;">Welcome to Terminal Monitor Base</h1>
  </td></tr>
  <tr><td style="padding:32px 36px;color:#e5e7eb;font-size:14px;line-height:1.7;">
    <p style="margin:0 0 20px;">Thanks for downloading Terminal Monitor. Base tier is free — no license key needed, just install and go.</p>
    <p style="margin:0 0 8px;color:#00ff64;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;">Setup</p>
    <ol style="margin:0 0 28px;padding-left:20px;color:#d1d5db;font-size:13px;line-height:1.8;">
      <li>Download the zip from <a href="https://github.com/annointedfrom/terminal-monitor/releases/latest" style="color:#00ff64;">github.com/annointedfrom/terminal-monitor</a></li>
      <li>Extract and run: <span style="color:#00ff64;">.venv\\Scripts\\uvicorn termmon.main:app --port 8084</span></li>
      <li>Open <span style="color:#00ff64;">http://localhost:8084</span> and complete the setup wizard</li>
    </ol>
    <p style="margin:0 0 8px;color:#00ff64;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;">What you get</p>
    <ul style="margin:0 0 28px;padding-left:20px;color:#d1d5db;font-size:13px;line-height:1.8;">${features}</ul>
    <p style="margin:0 0 20px;color:#9ca3af;font-size:13px;">Upgrade to Mid or Diamond anytime for memory server, plugin support, and brain sync.<br>
    <a href="https://landing-eight-rho-26.vercel.app" style="color:#00ff64;">See all tiers</a></p>
    <p style="margin:0;color:#9ca3af;font-size:13px;">Questions? Reply here — I respond within 24h.<br>— Angel Vaquera Jr.</p>
  </td></tr>
  <tr><td style="border-top:1px solid rgba(0,255,100,0.1);padding:18px 36px;">
    <p style="margin:0;color:#4b5563;font-size:11px;">Terminal Monitor · <a href="https://landing-eight-rho-26.vercel.app" style="color:#4b5563;">landing-eight-rho-26.vercel.app</a></p>
  </td></tr>
</table>
</td></tr></table>
</body></html>`
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'method_not_allowed' })
  }

  const secret = req.query.secret as string | undefined
  if (!secret || secret !== process.env.GUMROAD_WEBHOOK_SECRET) {
    return res.status(401).json({ error: 'unauthorized' })
  }

  const { email, product_permalink: permalink, test } = req.body ?? {}

  if (!email || !permalink) {
    return res.status(400).json({ error: 'missing_fields' })
  }

  if (test === 'true' || test === true) {
    console.log(`[gumroad-webhook] test purchase ignored for ${email}`)
    return res.status(200).json({ ok: true, skipped: 'test_purchase' })
  }

  const tier = PERMALINK_TO_TIER[permalink as string]
  if (!tier) {
    console.error(`[gumroad-webhook] unknown permalink: ${permalink}`)
    return res.status(400).json({ error: 'unknown_product' })
  }

  try {
    const resend = new Resend(process.env.RESEND_API_KEY)
    const from = process.env.RESEND_FROM_EMAIL!

    if (tier === 'base') {
      await resend.emails.send({
        from,
        to: email as string,
        subject: "Terminal Monitor Base — you're all set",
        html: welcomeEmail(),
      })
    } else {
      const licenseKey = jwt.sign(
        {
          tier,
          email,
          issued_at: new Date().toISOString().split('T')[0],
          sub: 'terminal-monitor',
          exp: EXP_2099,
        },
        process.env.TERMMON_PRIVATE_KEY!,
        { algorithm: 'RS256' },
      )

      await resend.emails.send({
        from,
        to: email as string,
        subject: `Terminal Monitor ${TIER_LABEL[tier]} — your license key`,
        html: keyEmail(email as string, tier, licenseKey),
      })
    }

    console.log(`[gumroad-webhook] delivered to ${email} (${tier})`)
    return res.status(200).json({ ok: true })
  } catch (err) {
    console.error('[gumroad-webhook] delivery failed:', err)
    return res.status(500).json({ error: 'delivery_failed' })
  }
}

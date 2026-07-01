const assert = require('node:assert/strict')
const { chromium } = require('playwright')

// Standalone Playwright smoke test for the Profiles edit drawer.
// Requires `playwright` to be available to Node, or run it through the Codex
// Playwright skill runner.
const HUD_URL = process.env.HUD_URL || 'http://localhost:5173'

const initialProfile = {
  name: 'default',
  is_default: true,
  model: 'gpt-5.5',
  provider: 'openai-codex',
  base_url: 'https://chatgpt.com/backend-api/codex',
  port: null,
  toolsets: ['hermes-cli'],
  skin: 'pirate',
  context_length: 0,
  soul_summary: 'Original soul',
  session_count: 12,
  message_count: 120,
  tool_call_count: 30,
  total_input_tokens: 1000,
  total_output_tokens: 200,
  total_tokens: 1200,
  last_active: null,
  memory_entries: 1,
  memory_chars: 20,
  memory_max_chars: 2200,
  user_entries: 1,
  user_chars: 10,
  user_max_chars: 1375,
  skill_count: 4,
  cron_job_count: 1,
  api_keys: [],
  gateway_status: 'inactive',
  server_status: 'n/a',
  has_alias: false,
  compression_enabled: true,
  compression_model: '',
  is_local: false,
}

const initialEdit = {
  name: 'default',
  model: {
    provider: 'openai-codex',
    default: 'gpt-5.5',
    base_url: 'https://chatgpt.com/backend-api/codex',
    api_mode: '',
    context_length: null,
  },
  toolsets: ['hermes-cli'],
  skin: 'pirate',
  compression: {
    enabled: true,
    summary_provider: '',
    summary_model: '',
  },
  soul: '# Original soul\n',
}

async function main() {
  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || process.env.CHROME_PATH
  const browser = await chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
  })
  try {
    const page = await browser.newPage({ viewport: { width: 1360, height: 950 } })

    let savedPayload = null
    let profile = { ...initialProfile }
    let profiles = [profile]
    let editPayload = structuredClone(initialEdit)
    let confirmDeleteBody = null
    let activeProfile = 'default'

    await page.addInitScript(() => {
      sessionStorage.setItem('hud-booted', 'true')
      localStorage.setItem('hermes-hudui-lang', 'en')
    })

    await page.route('**/api/dashboard', async () => {
      // Leave the dashboard in its loading state until the test switches tabs.
    })

    await page.route('**/api/profiles/options', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          providers: ['openai-codex', 'anthropic', 'openrouter', 'zai', 'custom'],
          toolsets: ['hermes-cli', 'web', 'browser', 'terminal', 'file', 'skills', 'memory'],
        }),
      })
    })

    await page.route('**/api/profiles/default/edit', async route => {
      const request = route.request()
      if (request.method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(editPayload),
        })
        return
      }

      if (request.method() === 'PUT') {
        savedPayload = request.postDataJSON()
        editPayload = {
          name: 'default',
          ...savedPayload,
        }
        profile = {
          ...profile,
          model: savedPayload.model.default,
          provider: savedPayload.model.provider,
          base_url: savedPayload.model.base_url,
          context_length: savedPayload.model.context_length || 0,
          toolsets: savedPayload.toolsets,
          skin: savedPayload.skin,
          soul_summary: 'Updated soul',
          compression_enabled: savedPayload.compression.enabled,
          compression_model: savedPayload.compression.summary_model,
        }
        profiles = profiles.map(item => item.name === 'default' ? profile : item)
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(editPayload),
        })
        return
      }

      await route.fulfill({ status: 405, body: 'method not allowed' })
    })

    await page.route('**/api/profiles/work/edit', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...initialEdit,
          name: 'work',
          model: { ...initialEdit.model, default: 'gpt-5.5' },
          soul: '# Work profile\n',
        }),
      })
    })

    await page.route('**/api/profiles/imported/edit', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...initialEdit,
          name: 'imported',
          model: { ...initialEdit.model, default: 'gpt-imported' },
          soul: '# Imported profile\n',
        }),
      })
    })

    await page.route('**/api/profiles', async route => {
      const request = route.request()
      if (request.method() === 'POST') {
        const body = request.postDataJSON()
        assert.deepEqual(body, { name: 'work', use_default_template: true })
        const created = {
          ...initialProfile,
          name: 'work',
          is_default: false,
          model: 'gpt-5.5',
          soul_summary: 'Work profile',
          session_count: 0,
          message_count: 0,
          tool_call_count: 0,
        }
        profiles = [...profiles, created]
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ...initialEdit,
            name: 'work',
          }),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          profiles,
          total: profiles.length,
          active_count: 0,
        }),
      })
    })

    await page.route('**/api/profiles/active', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ active_profile: activeProfile }),
      })
    })

    await page.route('**/api/profiles/import', async route => {
      const body = route.request().postDataJSON()
      assert.equal(body.name, 'imported')
      assert.equal(body.config_yaml, 'model:\n  default: gpt-imported\n')
      assert.equal(body.soul, '# Imported profile')
      profiles = [
        ...profiles,
        {
          ...initialProfile,
          name: 'imported',
          is_default: false,
          model: 'gpt-imported',
          soul_summary: 'Imported profile',
        },
      ]
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...initialEdit,
          name: 'imported',
        }),
      })
    })

    await page.route('**/api/profiles/work/use', async route => {
      assert.equal(route.request().method(), 'POST')
      activeProfile = 'work'
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ active_profile: 'work' }),
      })
    })

    await page.route('**/api/profiles/imported', async route => {
      const request = route.request()
      assert.equal(request.method(), 'DELETE')
      confirmDeleteBody = request.postDataJSON()
      profiles = profiles.filter(item => item.name !== 'imported')
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, name: 'imported' }),
      })
    })

    await page.goto(HUD_URL, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: /Profiles/i }).click()
    await page.getByRole('button', { name: /^Edit$/ }).click()

    const editor = page.locator('[data-profile-editor="default"]')
    await editor.locator('input[list="profile-provider-options"]').fill('anthropic')

    const modelInputs = editor.locator('input.w-full')
    await modelInputs.nth(1).fill('claude-opus-4.6')
    await modelInputs.nth(2).fill('200000')
    await modelInputs.nth(3).fill('https://api.anthropic.com')
    await modelInputs.nth(4).fill('messages')
    await modelInputs.nth(5).fill('blade-runner')

    await page.getByRole('button', { name: 'web' }).click()
    await page.getByRole('button', { name: 'browser' }).click()
    await editor.locator('input[placeholder="Add custom toolset"]').fill('custom-tools')
    await editor.getByRole('button', { name: /^Add$/ }).click()

    const compressionCheckbox = editor.getByRole('checkbox', { name: /^Compress$/ })
    if (!(await compressionCheckbox.isChecked())) {
      await compressionCheckbox.check()
    }
    await modelInputs.nth(6).fill('anthropic')
    await modelInputs.nth(7).fill('claude-opus-4.6')

    await editor.locator('textarea').fill('# Updated soul\n\nUse the edited profile instructions.')
    await editor.getByRole('button', { name: /^Save$/ }).click()
    await page.waitForFunction(() => document.body.textContent.includes('claude-opus-4.6'))

    assert.deepEqual(savedPayload, {
      model: {
        provider: 'anthropic',
        default: 'claude-opus-4.6',
        base_url: 'https://api.anthropic.com',
        api_mode: 'messages',
        context_length: 200000,
      },
      toolsets: ['hermes-cli', 'web', 'browser', 'custom-tools'],
      skin: 'blade-runner',
      compression: {
        enabled: true,
        summary_provider: 'anthropic',
        summary_model: 'claude-opus-4.6',
      },
      soul: '# Updated soul\n\nUse the edited profile instructions.',
    })

    await page.locator('input[placeholder="work"]').fill('work')
    await page.getByRole('button', { name: /^Add profile$/ }).click()
    await page.waitForFunction(() => document.body.textContent.includes('Work profile'))

    const workCard = page.locator('[data-profile-name="work"]')
    await workCard.getByRole('button', { name: /^Use profile$/ }).click()
    await page.waitForFunction(() => document.body.textContent.includes('current'))

    await page.getByRole('button', { name: /^Import$/ }).first().click()
    await page.locator('input[placeholder="imported"]').fill('imported')
    await page.locator('[data-profile-import-config]').fill('model:\n  default: gpt-imported\n')
    await page.locator('[data-profile-import-soul]').fill('# Imported profile')
    await page.getByRole('button', { name: /^Import$/ }).last().click()
    await page.waitForFunction(() => document.body.textContent.includes('Imported profile'))

    const importedCard = page.locator('[data-profile-name="imported"]')
    await importedCard.getByRole('button', { name: /^Delete$/ }).click()
    await importedCard.getByRole('button', { name: /^Confirm delete$/ }).click()
    await page.waitForFunction(() => !document.body.textContent.includes('Imported profile'))
    assert.deepEqual(confirmDeleteBody, { confirm_name: 'imported' })

    console.log('Profile edit E2E passed')
  } finally {
    await browser.close()
  }
}

main().catch(error => {
  console.error(error)
  process.exit(1)
})

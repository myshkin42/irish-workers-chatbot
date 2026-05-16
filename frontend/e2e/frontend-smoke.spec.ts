import { expect, type Page, type Route, test } from '@playwright/test';

const API_ORIGIN = 'http://localhost:8000';

const corsHeaders = {
  'access-control-allow-origin': '*',
  'access-control-allow-headers': 'content-type',
  'access-control-allow-methods': 'GET,POST,OPTIONS',
  'content-type': 'application/json',
};

const metadata = {
  disclaimer: 'This chatbot provides general information about Irish employment law. It is not legal advice.',
  knowledge_base_updated: '2026-03-06',
  knowledge_base_version: '1.0.0',
  time_limits_warning: "Most WRC complaints must be made within 6 months of the incident. Don't delay seeking advice.",
  official_sources: [
    {
      name: 'Workplace Relations Commission',
      url: 'https://www.workplacerelations.ie',
      description: 'File complaints, find guides and codes of practice',
    },
    {
      name: 'Citizens Information',
      url: 'https://www.citizensinformation.ie/en/employment/',
      description: 'Plain-language guides on employment rights',
    },
  ],
  important_contacts: {
    wrc_info_line: '0818 80 80 90',
    wrc_online_complaints: 'https://www.workplacerelations.ie/en/complaints_disputes/refer_a_dispute_make_a_complaint/',
    hsa_contact: 'https://www.hsa.ie',
    citizens_info_phone: '0818 07 4000',
  },
};

const officialLinks = [
  {
    name: 'Workplace Relations Commission',
    url: 'https://www.workplacerelations.ie',
    description: 'File complaints, find guides and codes of practice',
  },
  {
    name: 'Citizens Information',
    url: 'https://www.citizensinformation.ie/en/employment/',
    description: 'Plain-language guides on employment rights',
  },
];

const longHoursAnswer = [
  'START OF HOURS ANSWER',
  '',
  'Under Irish employment law, your average working time should not normally exceed 48 hours per week. You are also entitled to daily rest, weekly rest, and breaks during the working day.',
  '',
  'This first part is the important bit the user should see when the answer arrives. The rest of this mocked answer is intentionally long so the smoke test can catch the old behavior where the viewport jumped to the end.',
  '',
  'Working-time questions can involve maximum hours, rest breaks, Sunday work, rosters, records of hours, and whether overtime is being counted correctly.',
  '',
  'If your employer cannot provide normal rest because of exceptional circumstances, they should provide compensatory rest as soon as possible afterwards.',
  '',
  'For a specific answer, the worker can say how many hours they work each day, whether they get breaks, and whether the issue is pay, recording, or rest.',
  '',
  'END OF HOURS ANSWER',
].join('\n\n');

function chatResponse(overrides: Record<string, unknown>) {
  return {
    answer: 'Default mocked answer',
    sources: [],
    official_links: officialLinks,
    has_authoritative_sources: true,
    lookup_context_expired: false,
    redirect_category: 'none',
    detected_company: null,
    ...overrides,
  };
}

function companyCheckResponse(company: string) {
  return {
    lookup_id: 'lookup-tesco-1',
    result: {
      company,
      summary: {
        total_records: 2,
        hsa_prosecutions: 0,
        decision_records: 2,
        wrc_decisions: 1,
        labour_court_records: 1,
        eat_records: 0,
        equality_records: 0,
      },
      source_status: {
        hsa: 'ok',
        wrc: 'ok',
        labour_court: 'ok',
        eat: 'ok',
        equality: 'ok',
      },
      partial_results: false,
      warnings: [
        'A result means the company name appears in a public workplace record; read the linked source before drawing conclusions.',
      ],
      records: [
        {
          source: 'wrc',
          body: 'wrc',
          source_name: 'Workplace Relations Commission',
          company_name: 'Tesco Ireland Limited',
          matched_as: 'defendant',
          case_number: 'ADJ-00058272',
          case_category: 'Adjudication',
          date: '16/02/2026',
          outcome_status: 'not_extracted',
          legislation: [],
          url: 'https://example.test/wrc-record',
          confidence: 'high',
        },
        {
          source: 'labour_court',
          body: 'labour_court',
          source_name: 'Labour Court',
          company_name: 'Tesco Ireland',
          matched_as: 'defendant',
          case_number: 'LCR12345',
          case_category: 'Determination',
          date: '10/01/2025',
          outcome_status: 'not_extracted',
          legislation: [],
          url: 'https://example.test/labour-court-record',
          confidence: 'high',
        },
      ],
    },
  };
}

async function fulfillJson(route: Route, body: unknown, status = 200, delayMs = 0) {
  if (delayMs) {
    await new Promise(resolve => setTimeout(resolve, delayMs));
  }
  await route.fulfill({
    status,
    headers: corsHeaders,
    body: JSON.stringify(body),
  });
}

async function mockApi(page: Page) {
  await page.route(`${API_ORIGIN}/**`, async route => {
    const request = route.request();
    if (request.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }

    const url = new URL(request.url());
    if (url.pathname === '/metadata') {
      await fulfillJson(route, metadata);
      return;
    }

    if (url.pathname === '/feedback' || url.pathname === '/api/records-redirect-click') {
      await fulfillJson(route, { ok: true });
      return;
    }

    if (url.pathname === '/api/company-check') {
      const payload = JSON.parse(request.postData() || '{}');
      await fulfillJson(route, companyCheckResponse(payload.company || 'Tesco'), 200, 150);
      return;
    }

    if (url.pathname === '/chat') {
      const payload = JSON.parse(request.postData() || '{}');
      const message = String(payload.message || '').toLowerCase();

      if (message.includes('has tesco been prosecuted')) {
        await fulfillJson(route, chatResponse({
          answer: "That's a question for the Check Public Records tab. It searches public records from the HSA, WRC, Labour Court, Employment Appeals Tribunal, and Equality Tribunal.\n\nUse the button below to open that check with **Tesco** pre-filled.",
          official_links: [],
          redirect_category: 'active_redirect',
          detected_company: 'Tesco',
        }));
        return;
      }

      if (message.includes('i work at tesco')) {
        await fulfillJson(route, chatResponse({
          answer: 'Your employer still has to follow working-time rules. If you are worried about your hours, check your roster, breaks, and whether your average weekly hours are above the legal limit.',
          sources: [{ title: 'Ci Working Hours', doc_type: 'guide' }],
          redirect_category: 'passive_mention',
          detected_company: 'Tesco',
        }));
        return;
      }

      if (message.includes('wondering about my hours')) {
        await fulfillJson(route, chatResponse({
          answer: longHoursAnswer,
          sources: [
            { title: 'Code Of Practice On Compensatory Rest Periods', doc_type: 'code_of_practice' },
            { title: 'Ci Work Breaks And Rest Periods', doc_type: 'guide' },
          ],
        }));
        return;
      }

      if (message.includes('minimum wage')) {
        await fulfillJson(route, chatResponse({
          answer: 'The national minimum wage in Ireland is shown in the Citizens Information minimum wage guide. Younger workers can have lower age-based rates.',
          sources: [{ title: 'Ci Minimum Wage', doc_type: 'guide' }],
        }));
        return;
      }

      await fulfillJson(route, chatResponse({
        answer: 'I can help with Irish employment rights.',
        sources: [{ title: 'Ci Employment Rights', doc_type: 'guide' }],
      }));
      return;
    }

    await route.fulfill({ status: 404, headers: corsHeaders, body: JSON.stringify({ detail: 'Not mocked' }) });
  });
}

async function openApp(page: Page) {
  await mockApi(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: "Irish Workers' Rights Chatbot" })).toBeVisible();
}

async function ask(page: Page, message: string) {
  await page.getByTestId('chat-input').fill(message);
  await page.getByTestId('send-button').click();
}

test('basic chat renders answer, sources, and feedback controls', async ({ page }) => {
  await openApp(page);

  await ask(page, 'What is the minimum wage?');

  const assistant = page.getByTestId('message-assistant').last();
  await expect(assistant).toContainText('national minimum wage');
  await expect(assistant).toContainText('Sources:');
  await expect(assistant).toContainText('Ci Minimum Wage');
  await expect(assistant.getByRole('button', { name: 'Thumbs up' })).toBeVisible();
  await expect(assistant.getByRole('button', { name: 'Thumbs down' })).toBeVisible();

  await assistant.getByRole('button', { name: 'Thumbs up' }).click();
  await expect(assistant).toContainText('Thanks for your feedback');
});

test('active records redirect opens records tab with company prefilled', async ({ page }) => {
  await openApp(page);

  await ask(page, 'Has Tesco been prosecuted?');

  const redirectButton = page.getByTestId('records-redirect-button');
  await expect(redirectButton).toHaveText('Open Check Public Records for Tesco');

  await redirectButton.click();

  await expect(page.getByTestId('company-input')).toBeVisible();
  await expect(page.getByTestId('company-input')).toHaveValue('Tesco');
  await expect(page).toHaveURL(/tab=records/);
  await expect(page).toHaveURL(/company=Tesco/);
});

test('records lookup shows loading state, summary, cards, and source links', async ({ page }) => {
  await openApp(page);

  await page.getByTestId('records-tab').click();
  await page.getByTestId('company-input').fill('Tesco');
  await page.getByTestId('company-check-button').click();

  await expect(page.getByText('Checking public records...')).toBeVisible();
  await expect(page.getByTestId('company-results')).toBeVisible();
  await expect(page.getByText('Found 2 public records for "Tesco":')).toBeVisible();
  await expect(page.getByText('WRC ADJUDICATION RECORD')).toBeVisible();
  await expect(page.getByText('LABOUR COURT DETERMINATION')).toBeVisible();
  await expect(page.getByRole('link', { name: 'View source record' })).toHaveCount(2);
  await expect(page.getByTestId('open-chat-with-results')).toBeEnabled();
});

test('passive records mention leaves user in chat and shows sidebar note', async ({ page }) => {
  await openApp(page);

  await ask(page, "I work at Tesco and I'm worried about my hours");

  const assistant = page.getByTestId('message-assistant').last();
  await expect(assistant).toContainText('working-time rules');
  await expect(assistant).toContainText('You can also check public records for Tesco');
  await expect(page.getByTestId('chat-input')).toBeVisible();
  await expect(page.getByTestId('company-input')).toBeHidden();
});

test.describe('mobile layout', () => {
  test.use({ viewport: { width: 375, height: 667 }, isMobile: true });

  test('resources drawer opens and broad replies anchor at their start', async ({ page }) => {
    await openApp(page);

    await page.getByRole('button', { name: 'Open resources panel' }).click();
    await expect(page.locator('.sidebar')).toHaveClass(/sidebar-open/);
    await expect(page.getByRole('heading', { name: 'Official Sources' })).toBeVisible();
    await page.getByRole('button', { name: 'Close sidebar' }).click();
    await expect(page.locator('.sidebar')).not.toHaveClass(/sidebar-open/);
    await expect(page.locator('.sidebar-overlay')).toHaveCount(0);

    await ask(page, 'I am wondering about my hours');

    await expect(page.getByText('START OF HOURS ANSWER')).toBeInViewport({ ratio: 0.5 });
    await expect(page.getByText('END OF HOURS ANSWER')).not.toBeInViewport();
    await expect(page.getByTestId('chat-input')).toBeInViewport();
    await expect(page.getByTestId('send-button')).toBeInViewport();
  });
});

import { expect, test, type Page } from '@playwright/test';

// The example study (examples/kb/fixture): A = "initial", B = "feature: refunds".
const A = 'b42f63fb2414b4d4d830af722a64255504a80ee8';
const B = '074ec965eabffb43a0224ef9f1426515d2818975';

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const hashIs = (h: string) => new RegExp(`${esc(h)}$`);

/** Lines highlighted by the route range in the code view. */
const rangeLines = (page: Page) => page.locator('.cm-editor .cm-rc-range');

function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  return errors;
}

test('flujo completo del visor', async ({ page, request }) => {
  const errors = trackErrors(page);
  const tree = page.getByTestId('file-tree');
  const explain = page.getByTestId('explain-panel');
  const codePath = page.getByTestId('code-path');
  const commit = page.getByRole('combobox', { name: 'Commit' });
  const tab = (name: string) => page.getByRole('tab', { name, exact: true });

  await test.step('lista de estudios → abrir «fixture»', async () => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Estudios' })).toBeVisible();
    await page.getByRole('link', { name: 'Fixture multilenguaje' }).click();
    await expect(page).toHaveURL(hashIs('#/fixture'));
    await expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');
  });

  await test.step('overview: mermaid y archify', async () => {
    const overview = page.getByTestId('overview');
    await expect(overview.getByRole('heading', { name: 'Fixture multilenguaje' })).toBeVisible();
    await expect(overview.locator('.rc-mermaid svg').first()).toBeVisible();
    const iframe = overview.locator('.rc-archify iframe');
    await expect(iframe).toHaveAttribute('src', /diagrams\/arquitectura\.html$/);
    await iframe.scrollIntoViewIfNeeded();
    await expect(iframe.contentFrame().locator('svg').first()).toBeVisible();
  });

  await test.step('árbol: abrir app/main.py', async () => {
    await tree.locator('[data-path="app"]').click();
    await tree.locator('[data-path="app/main.py"]').click();
    await expect(page).toHaveURL(hashIs(`#/fixture/${B}/f/app/main.py`));
    await expect(codePath).toHaveText('app/main.py');
    await expect(page.locator('.cm-content')).toContainText('def main');
    await expect(explain.getByRole('heading', { name: 'main.py' })).toBeVisible();
    await expect(explain.locator('[data-block]')).toHaveCount(3);
  });

  await test.step('clic en un bloque → resalta su rango', async () => {
    const card = explain.locator('[data-block="b2"]');
    await card.locator('.chip').click();
    await expect(page).toHaveURL(hashIs(`#/fixture/${B}/f/app/main.py:L4-7`));
    await expect(rangeLines(page)).toHaveCount(4);
    await expect(rangeLines(page).first()).toHaveText('def main():');
    await expect(card).toHaveClass(/active/);
  });

  await test.step('ref exacta → archivo y rango destino; atrás vuelve', async () => {
    await explain.locator('[data-block="b1"] a.rc-ref[href$="/f/app/services/auth.py:L5-7"]').click();
    await expect(page).toHaveURL(hashIs(`#/fixture/${B}/f/app/services/auth.py:L5-7`));
    await expect(codePath).toHaveText('app/services/auth.py');
    await expect(rangeLines(page)).toHaveCount(3);
    await expect(page.locator('.cm-content')).toContainText('def process');

    await page.goBack();
    await expect(page).toHaveURL(hashIs(`#/fixture/${B}/f/app/main.py:L4-7`));
    await expect(codePath).toHaveText('app/main.py');
    await expect(rangeLines(page)).toHaveCount(4);
  });

  await test.step('ref ambigua → menú de candidatos', async () => {
    await tab('Overview').click();
    const ambiguous = page.getByTestId('overview').locator('button.rc-ambiguous').first();
    await ambiguous.scrollIntoViewIfNeeded();
    await ambiguous.click();
    const menu = page.getByRole('menu');
    await expect(menu).toBeVisible();
    await expect(menu.getByRole('menuitem')).toHaveCount(2);
    await expect(menu.getByRole('menuitem', { name: /app\/services\/auth\.py/ })).toBeVisible();
    await expect(menu.getByRole('menuitem', { name: /app\/services\/billing\.py/ })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(menu).toHaveCount(0);
  });

  await test.step('primer commit → tour «Flujo de facturación» hasta el paso 3', async () => {
    await commit.selectOption(A);
    await expect(page).toHaveURL(new RegExp(`#/fixture/${A}/?$`));
    await tab('Tours').click();
    const card = page.getByTestId('tours').locator('section', { hasText: 'Flujo de facturación' });
    await card.getByTestId('tour-start').click();
    await expect(page).toHaveURL(hashIs(`#/fixture/${A}/tour/flujo-facturacion/1`));
    const panel = page.getByTestId('tour-panel');
    await expect(panel).toContainText('paso 1 de 5');
    await panel.getByRole('link', { name: '▶' }).click();
    await expect(panel).toContainText('paso 2 de 5');
    await panel.getByRole('link', { name: '▶' }).click();
    await expect(page).toHaveURL(hashIs(`#/fixture/${A}/tour/flujo-facturacion/3`));
    await expect(panel).toContainText('paso 3 de 5');
    await expect(panel.getByRole('heading', { name: 'Facturación: del usuario al total' })).toBeVisible();
    await expect(codePath).toHaveText('app/services/billing.py');
    await expect(rangeLines(page)).toHaveCount(3);
    await expect(rangeLines(page).first()).toHaveText('def process(user, items):');
    await expect(tree.locator('[data-path="app/services/billing.py"]')).toHaveAttribute('aria-selected', 'true');
  });

  await test.step('salir del tour y pasar al segundo commit → billing.py muestra el reembolso', async () => {
    await page.getByTestId('tour-panel').getByRole('link', { name: /salir del tour/ }).click();
    await expect(page).toHaveURL(hashIs(`#/fixture/${A}/f/app/services/billing.py:L8-10`));
    await expect(explain.locator('[data-block]')).toHaveCount(3);

    await commit.selectOption(B);
    await expect(page).toHaveURL(hashIs(`#/fixture/${B}/f/app/services/billing.py:L8-10`));
    await expect(codePath).toHaveText('app/services/billing.py');
    await expect(page.locator('.cm-content')).toContainText('def refund');
    await expect(explain.locator('[data-block="b4"]')).toContainText('refund(): un reembolso es una factura negativa');
  });

  await test.step('Comparar… → vista de diff', async () => {
    await page.getByRole('button', { name: 'Comparar…' }).click();
    const dialog = page.getByRole('dialog', { name: 'Comparar commits' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('status')).toHaveText('Diff disponible.');
    await dialog.getByRole('button', { name: 'Comparar', exact: true }).click();
    await expect(page).toHaveURL(hashIs(`#/fixture/diff/${A}..${B}`));

    // only the changed files, each with its badge
    const rows = tree.locator('button.row.file');
    await expect(rows).toHaveCount(4);
    const badges = Object.fromEntries(
      await Promise.all(
        (await rows.all()).map(async (r) => [await r.getAttribute('data-path'), (await r.locator('.badge').innerText()).trim()]),
      ),
    );
    expect(badges).toEqual({
      'app/services/billing.py': 'M',
      'app/services/refunds.py': 'A',
      'db/queries.sql': 'D',
      'web/src/api.ts': 'M',
    });
    await expect(tree.locator('[data-path="app/main.py"]')).toHaveCount(0);

    // global explanation
    const diffPanel = page.getByTestId('diff-panel');
    await expect(diffPanel.getByRole('heading', { name: /^Cambios b42f63f → 074ec96/ })).toBeVisible();
    await expect(diffPanel.locator('.markdown').first()).not.toBeEmpty();

    // one file: merge view + its hunk explanation
    await tree.locator('[data-path="app/services/billing.py"]').click();
    await expect(page).toHaveURL(hashIs(`#/fixture/diff/${A}..${B}/app/services/billing.py`));
    await expect(page.locator('.cm-mergeView')).toBeVisible();
    await expect(page.locator('.cm-mergeView .cm-editor')).toHaveCount(2);
    await expect(page.locator('.cm-mergeView')).toContainText('def refund');
    const hunk = diffPanel.locator('section.card').first();
    await expect(hunk).toContainText('@@');
    await expect(hunk.locator('.markdown')).not.toBeEmpty();
    await expect(hunk.locator('.none')).toHaveCount(0);

    await page.getByRole('button', { name: 'salir de la comparación' }).click();
    await expect(page).toHaveURL(hashIs(`#/fixture/${B}/f/app/services/billing.py`));
  });

  await test.step('pestaña Grafo', async () => {
    // Only this step depends on graph.json (test.skip here would skip the rest of the flow).
    const graph = await request.get(`/kb/fixture/snapshots/${B}/graph/graph.json`);
    if (!graph.ok()) {
      test.info().annotations.push({ type: 'skip', description: 'el ejemplo no tiene graph.json: Grafo sin comprobar' });
      await expect(tab('Grafo')).toHaveCount(0);
      return;
    }
    await tab('Grafo').click();
    await expect(page).toHaveURL(hashIs(`#/fixture/${B}/graph`));
    const view = page.getByTestId('graph-view');
    await expect(view.locator('.communities li').first()).toBeVisible();
    await expect(view.locator('.canvas canvas').first()).toBeVisible();
  });

  await test.step('Ctrl+K «refund» → navegar', async () => {
    await tab('Código').click();
    await page.locator('body').click({ position: { x: 5, y: 5 } });
    await page.keyboard.press('Control+k');
    const palette = page.getByRole('dialog', { name: 'Buscar' });
    await expect(palette).toBeVisible();
    await palette.getByRole('combobox', { name: 'Buscar' }).fill('refund');
    const first = palette.getByRole('option').first();
    await expect(first).toContainText('refund');
    await expect(first).toContainText('símbolo');
    await page.keyboard.press('Enter');
    await expect(palette).toHaveCount(0);
    await expect(page).toHaveURL(hashIs(`#/fixture/${B}/f/app/services/billing.py:L13-15`));
    await expect(rangeLines(page)).toHaveCount(3);
  });

  expect(errors).toEqual([]);
});

test('tours: volver a la lista y reabrir el mismo tour; pasos seguidos en el mismo archivo', async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto(`/#/fixture/${B}/tour/flujo-facturacion/1`);
  const panel = page.getByTestId('tour-panel');
  await expect(panel).toContainText('paso 1 de 7');

  // the player → Tours tab shows the list without changing the hash…
  await page.getByRole('tab', { name: 'Tours', exact: true }).click();
  await expect(panel).toHaveCount(0);
  const start = page.getByTestId('tours').locator('section', { hasText: 'Flujo de facturación' }).getByTestId('tour-start');
  await expect(start).toBeVisible();
  // …and starting the same tour (same hash) must leave the list
  await start.click();
  await expect(panel).toContainText('paso 1 de 7');
  await expect(page.getByTestId('code-path')).toHaveText('app/main.py');

  // worker-cola steps 2 → 3 → 4 stay on worker/queue.go with different ranges
  await page.goto(`/#/fixture/${B}/tour/worker-cola/2`);
  await expect(panel).toContainText('paso 2 de 5');
  const marked = page.locator('.cm-editor .cm-rc-range');
  await expect(marked).toHaveText(['type Queue struct {', '	items []string', '}']);
  await page.keyboard.press(']');
  await expect(panel).toContainText('paso 3 de 5');
  await expect(marked).toHaveText(['func NewQueue() *Queue {', '	return &Queue{}', '}']);
  await panel.getByRole('link', { name: '▶' }).click();
  await expect(panel).toContainText('paso 4 de 5');
  await expect(marked).toHaveText(['func (q *Queue) Push(item string) {', '	q.items = append(q.items, item)', '}']);
  await expect(marked.first()).toBeInViewport();
  expect(errors).toEqual([]);
});

test('compare dialog desde el commit más antiguo; Ctrl+K no abre la búsqueda bajo el diálogo', async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto(`/#/fixture/${A}/`);
  await expect(page.getByTestId('overview')).toBeVisible();
  await page.getByRole('button', { name: 'Comparar…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Comparar commits' });
  await expect(dialog.getByRole('status')).toHaveText('Diff disponible.');

  // Ctrl+K with the modal open: the palette must stay closed over a short window…
  const palette = page.getByRole('dialog', { name: 'Buscar' });
  await page.keyboard.press('Control+k');
  for (let i = 0; i < 6; i++) {
    expect(await palette.count()).toBe(0);
    await page.waitForTimeout(100);
  }
  // …while the same keypress does open it once the dialog is closed.
  await dialog.getByRole('button', { name: 'Cancelar' }).click();
  await expect(dialog).toHaveCount(0);
  await page.keyboard.press('Control+k');
  await expect(palette).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(palette).toHaveCount(0);

  await page.getByRole('button', { name: 'Comparar…' }).click();
  await expect(dialog.getByRole('status')).toHaveText('Diff disponible.');
  await dialog.getByRole('button', { name: 'Comparar', exact: true }).click();
  await expect(page).toHaveURL(hashIs(`#/fixture/diff/${A}..${B}`));
  expect(errors).toEqual([]);
});

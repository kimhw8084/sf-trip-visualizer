import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workspace = process.cwd();
const inputPath = path.join(workspace, "SF_Trip_FINAL_SELECTION_50Criteria_2026-09-13.xlsx");
const outputDir = path.join(workspace, ".audit_workbook");
await fs.mkdir(outputDir, { recursive: true });

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheetSummary = await workbook.inspect({
  kind: "workbook,sheet,definedName,drawing,thread",
  maxChars: 60000,
  tableMaxRows: 8,
  tableMaxCols: 12,
  tableMaxCellChars: 200,
  options: { maxResults: 1000 },
});
await fs.writeFile(path.join(outputDir, "workbook_structure.ndjson"), `${sheetSummary.ndjson}\n`);

const sheets = workbook.worksheets.items;
const manifest = [];
for (const sheet of sheets) {
  const used = sheet.getRange("A1:AQ231");
  const address = used?.address ?? null;
  const values = used?.values ?? [];
  const formulas = used?.formulas ?? [];
  const displayFormulas = used?.displayFormulas ?? [];
  const record = {
    name: sheet.name,
    id: sheet.sheetId,
    address,
    visibility: sheet.visibility ?? null,
    showGridLines: sheet.showGridLines,
    rowCount: values.length,
    columnCount: values.reduce((max, row) => Math.max(max, row?.length ?? 0), 0),
    tables: (sheet.tables?.items ?? []).map((table) => ({
      name: table.name,
      range: table.getRange?.().address ?? null,
    })),
  };
  manifest.push(record);
  await fs.writeFile(
    path.join(outputDir, `${sheet.name.replace(/[^a-zA-Z0-9._-]+/g, "_")}.json`),
    `${JSON.stringify({ ...record, values, formulas, displayFormulas }, null, 2)}\n`,
  );
  for (let startRow = 1; startRow <= 231; startRow += 38) {
    const endRow = Math.min(231, startRow + 37);
    const render = await workbook.render({
      sheetName: sheet.name,
      range: `A${startRow}:AQ${endRow}`,
      scale: 0.65,
      format: "png",
    });
    await fs.writeFile(
      path.join(
        outputDir,
        `${sheet.name.replace(/[^a-zA-Z0-9._-]+/g, "_")}__rows_${String(startRow).padStart(3, "0")}_${String(endRow).padStart(3, "0")}.png`,
      ),
      new Uint8Array(await render.arrayBuffer()),
    );
  }
}

const formulas = await workbook.inspect({
  kind: "formula",
  maxChars: 100000,
  options: { maxResults: 5000 },
});
await fs.writeFile(path.join(outputDir, "formulas.ndjson"), `${formulas.ndjson}\n`);
await fs.writeFile(path.join(outputDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(JSON.stringify(manifest, null, 2));

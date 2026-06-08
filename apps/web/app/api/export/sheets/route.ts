/**
 * POST /api/export/sheets
 *
 * Creates a Google Spreadsheet from the provided table data and returns the URL.
 *
 * Required environment variables (add to .env):
 *   GOOGLE_SERVICE_ACCOUNT_EMAIL   — service account email
 *   GOOGLE_SERVICE_ACCOUNT_KEY     — private key (JSON-escaped, with literal \n)
 *   GOOGLE_SHEETS_SHARE_EMAIL      — (optional) auto-share the new sheet with this email
 *
 * Setup:
 *   1. Create a Google Cloud project → enable Sheets API + Drive API
 *   2. Create a service account → generate a JSON key
 *   3. Copy client_email → GOOGLE_SERVICE_ACCOUNT_EMAIL
 *   4. Copy private_key  → GOOGLE_SERVICE_ACCOUNT_KEY
 *   5. (optional) invite the service account's email to a shared Drive folder
 */

import { NextRequest, NextResponse } from "next/server";
import { google } from "googleapis";

type TablePayload = {
  title: string;
  headers: string[];
  rows: (string | number | boolean | null | undefined)[][];
};

type RequestBody = {
  title: string;
  tables: TablePayload[];
};

export async function POST(req: NextRequest) {
  // ── Validate env ────────────────────────────────────────────────────────────
  const serviceAccountEmail = process.env.GOOGLE_SERVICE_ACCOUNT_EMAIL;
  const privateKey          = process.env.GOOGLE_SERVICE_ACCOUNT_KEY?.replace(/\\n/g, "\n");

  if (!serviceAccountEmail || !privateKey) {
    return NextResponse.json(
      {
        error:
          "Google Sheets export is not configured. " +
          "Set GOOGLE_SERVICE_ACCOUNT_EMAIL and GOOGLE_SERVICE_ACCOUNT_KEY in .env.",
      },
      { status: 503 },
    );
  }

  // ── Parse body ──────────────────────────────────────────────────────────────
  let body: RequestBody;
  try {
    body = (await req.json()) as RequestBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { title, tables } = body;

  if (!Array.isArray(tables) || tables.length === 0) {
    return NextResponse.json({ error: "No tables provided" }, { status: 400 });
  }

  // ── Auth ────────────────────────────────────────────────────────────────────
  const auth = new google.auth.GoogleAuth({
    credentials: {
      client_email: serviceAccountEmail,
      private_key:  privateKey,
    },
    scopes: [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive.file",
    ],
  });

  const sheets = google.sheets({ version: "v4", auth });
  const drive  = google.drive({ version: "v3", auth });

  // ── Create spreadsheet ──────────────────────────────────────────────────────
  const created = await sheets.spreadsheets.create({
    requestBody: {
      properties: { title: title ?? "Incept Export" },
      sheets: tables.map((t, i) => ({
        properties: {
          sheetId: i,
          title:   t.title.slice(0, 100), // Sheets sheet title max 100 chars
        },
      })),
    },
  });

  const spreadsheetId = created.data.spreadsheetId!;

  // ── Populate each sheet ─────────────────────────────────────────────────────
  const valueData = tables.map((t) => ({
    range:  `'${t.title.slice(0, 100)}'!A1`,
    values: [
      t.headers,
      ...t.rows.map((row) =>
        row.map((cell) =>
          cell === null || cell === undefined ? "" : String(cell),
        ),
      ),
    ],
  }));

  await sheets.spreadsheets.values.batchUpdate({
    spreadsheetId,
    requestBody: {
      valueInputOption: "RAW",
      data:             valueData,
    },
  });

  // ── Bold header row in each sheet ───────────────────────────────────────────
  await sheets.spreadsheets.batchUpdate({
    spreadsheetId,
    requestBody: {
      requests: tables.map((_, i) => ({
        repeatCell: {
          range: {
            sheetId:          i,
            startRowIndex:    0,
            endRowIndex:      1,
            startColumnIndex: 0,
            endColumnIndex:   tables[i].headers.length,
          },
          cell: {
            userEnteredFormat: {
              textFormat: { bold: true },
              backgroundColor: { red: 0.96, green: 0.97, blue: 1 },
            },
          },
          fields: "userEnteredFormat(textFormat,backgroundColor)",
        },
      })),
    },
  });

  // ── Share with specified email (optional) ───────────────────────────────────
  const shareEmail = process.env.GOOGLE_SHEETS_SHARE_EMAIL;
  if (shareEmail) {
    try {
      await drive.permissions.create({
        fileId: spreadsheetId,
        requestBody: {
          role:         "writer",
          type:         "user",
          emailAddress: shareEmail,
        },
        // Suppress Google's notification email
        sendNotificationEmail: false,
      });
    } catch {
      // Non-fatal — file was created, sharing just didn't work
      console.warn("[sheets export] Could not share file with", shareEmail);
    }
  }

  const url = `https://docs.google.com/spreadsheets/d/${spreadsheetId}`;
  return NextResponse.json({ url, spreadsheetId });
}

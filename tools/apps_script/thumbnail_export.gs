/**
 * Read-only Google Apps Script helper for extracting in-cell thumbnails
 * from shot list spreadsheets without modifying the original sheets.
 *
 * Usage:
 * 1. Create a standalone Apps Script project under the same Google account
 *    that can access the spreadsheets.
 * 2. Paste this file into the project.
 * 3. Run `listSceneShotsWithThumbnails()` once from the editor to authorize.
 * 4. Optionally deploy as a Web App and call doGet with ?scene=0010
 *    or without params to return sceneList only.
 */

const MAIN_SPREADSHEET_ID = '1zgG3SmrmIQPusOCqVRk5i1WM-n6kEtk_U26bYjhdTl4';
const SCENE_LIST_SHEET_NAME = 'sceneList';

function doGet(e) {
  const sceneCode = e && e.parameter ? e.parameter.scene : '';
  const payload = sceneCode
    ? getSceneShotsWithThumbnails(sceneCode)
    : listScenes();

  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

function listScenes() {
  const sheet = SpreadsheetApp.openById(MAIN_SPREADSHEET_ID).getSheetByName(SCENE_LIST_SHEET_NAME);
  const values = sheet.getDataRange().getDisplayValues();
  const scenes = [];

  for (let rowIndex = 3; rowIndex < values.length; rowIndex++) {
    const row = values[rowIndex];
    const shotListUrl = row.find((cell) => String(cell).indexOf('/spreadsheets/d/') !== -1);
    const sceneCode = row[25] || '';
    if (!shotListUrl || !sceneCode) {
      continue;
    }

    scenes.push({
      scene_code: sceneCode,
      scene_label: row[0] || '',
      shotlist_name: row[1] || '',
      total_shots: toNumber(row[2]),
      total_minutes: toFloat(row[3]),
      total_seconds: toFloat(row[4]),
      total_frames: toNumber(row[5]),
      shotlist_url: shotListUrl,
      shotlist_spreadsheet_id: extractSpreadsheetId(shotListUrl),
    });
  }

  return {
    spreadsheet_title: SpreadsheetApp.openById(MAIN_SPREADSHEET_ID).getName(),
    worksheet_title: SCENE_LIST_SHEET_NAME,
    scenes,
  };
}

function getSceneShotsWithThumbnails(sceneCode) {
  const scenes = listScenes().scenes;
  const scene = scenes.find((item) => item.scene_code === sceneCode);
  if (!scene) {
    return { error: `Scene not found: ${sceneCode}` };
  }

  const spreadsheet = SpreadsheetApp.openById(scene.shotlist_spreadsheet_id);
  const sheetName = `${sceneCode}_Direction Note`;
  const sheet = spreadsheet.getSheetByName(sheetName) || spreadsheet.getSheets()[0];
  const range = sheet.getRange(5, 1, Math.max(sheet.getLastRow() - 4, 0), 3);
  const values = range.getValues();
  const displayValues = range.getDisplayValues();
  const shots = [];

  for (let i = 0; i < values.length; i++) {
    const shotValue = displayValues[i][0];
    if (!shotValue || shotValue.indexOf('_0000') !== -1) {
      continue;
    }

    const thumbCell = values[i][1];
    let thumbnail = null;

    if (thumbCell && thumbCell.valueType === SpreadsheetApp.ValueType.IMAGE) {
      thumbnail = {
        content_url: safeCall(() => thumbCell.getContentUrl()),
        alt_text: safeCall(() => thumbCell.getAltTextDescription()) || '',
        source_url: safeCall(() => thumbCell.getUrl()) || '',
      };
    }

    shots.push({
      shot_code: normalizeShotCode(sceneCode, shotValue),
      duration_frames: toNumber(displayValues[i][2]),
      preview_image_url: thumbnail ? (thumbnail.content_url || thumbnail.source_url || '') : '',
      preview_image_alt: thumbnail ? thumbnail.alt_text : '',
      source_sheet_title: spreadsheet.getName(),
      source_worksheet_title: sheet.getName(),
    });
  }

  return {
    scene_code: scene.scene_code,
    scene_label: scene.scene_label,
    shotlist_name: scene.shotlist_name,
    shotlist_url: scene.shotlist_url,
    shotlist_spreadsheet_id: scene.shotlist_spreadsheet_id,
    total_shots: scene.total_shots,
    total_minutes: scene.total_minutes,
    total_seconds: scene.total_seconds,
    total_frames: scene.total_frames,
    shots,
  };
}

function listSceneShotsWithThumbnails() {
  const scenes = listScenes().scenes;
  return scenes.map((scene) => getSceneShotsWithThumbnails(scene.scene_code));
}

function extractSpreadsheetId(url) {
  const match = String(url).match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  return match ? match[1] : '';
}

function normalizeShotCode(sceneCode, shotValue) {
  if (String(shotValue).indexOf(`${sceneCode}_`) === 0) {
    return shotValue;
  }
  return `${sceneCode}_${shotValue}`;
}

function toNumber(value) {
  const normalized = String(value || '').replace(/,/g, '');
  return normalized ? Number(normalized) : null;
}

function toFloat(value) {
  const normalized = String(value || '').replace(/,/g, '');
  return normalized ? Number(normalized) : null;
}

function safeCall(fn) {
  try {
    return fn();
  } catch (error) {
    return '';
  }
}

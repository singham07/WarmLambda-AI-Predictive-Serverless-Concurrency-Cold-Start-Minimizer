import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..');

const targetDirs = [
  path.join(rootDir, 'src'),
  path.join(rootDir, 'public')
];
const targetFiles = [
  path.join(rootDir, 'index.html')
];

const disallowedStrings = [
  'gradient',
  'border-radius: 9999',
  'border-radius:9999',
  'border-radius: 50px',
  'border-radius:50px',
  'border-radius: 999px',
  'border-radius:999px',
  'Made with',
  'Lorem',
  'testimonial'
];

const forbiddenFileNames = [
  'vite.svg',
  'react.svg',
  'hero.png'
];

// Helper to convert hex to HSL hue
function hexToHue(hex) {
  let clean = hex.replace('#', '');
  if (clean.length === 3) {
    clean = clean.split('').map(c => c + c).join('');
  }
  if (clean.length !== 6) return null;

  const r = parseInt(clean.substring(0, 2), 16) / 255;
  const g = parseInt(clean.substring(2, 4), 16) / 255;
  const b = parseInt(clean.substring(4, 6), 16) / 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;

  if (delta === 0) return null; // monochrome, no hue

  const lightness = (max + min) / 2;
  const saturation = delta / (1 - Math.abs(2 * lightness - 1));

  if (saturation < 0.1 || lightness < 0.05 || lightness > 0.95) {
    return null; // nearly black, white, or gray
  }

  let hue = 0;
  if (max === r) {
    hue = ((g - b) / delta) % 6;
  } else if (max === g) {
    hue = (b - r) / delta + 2;
  } else {
    hue = (r - g) / delta + 4;
  }
  hue = Math.round(hue * 60);
  if (hue < 0) hue += 360;
  return hue;
}

const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1FA00}-\u{1FAFF}]/u;

let errors = [];

function checkFileContent(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');

  lines.forEach((line, idx) => {
    const lineNum = idx + 1;

    // 1. Em dash (\u2014) or En dash (\u2013)
    if (line.includes('\u2014')) {
      errors.push(`${filePath}:${lineNum} contains forbidden em dash (\u2014)`);
    }
    if (line.includes('\u2013')) {
      errors.push(`${filePath}:${lineNum} contains forbidden en dash (\u2013)`);
    }

    // 2. Disallowed substrings
    for (const dis of disallowedStrings) {
      if (line.toLowerCase().includes(dis.toLowerCase())) {
        errors.push(`${filePath}:${lineNum} contains forbidden string "${dis}"`);
      }
    }

    // 3. Emoji
    if (emojiRegex.test(line)) {
      errors.push(`${filePath}:${lineNum} contains forbidden emoji character`);
    }

    // 4. Hex colors in violet/purple hue (250 to 320)
    const hexMatches = line.match(/#[0-9a-fA-F]{3,6}\b/g);
    if (hexMatches) {
      for (const hex of hexMatches) {
        const hue = hexToHue(hex);
        if (hue !== null && hue >= 250 && hue <= 320) {
          errors.push(`${filePath}:${lineNum} contains violet/purple color ${hex} (hue ${hue})`);
        }
      }
    }
  });
}

function scanDir(dir) {
  if (!fs.existsSync(dir)) return;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (forbiddenFileNames.includes(entry.name)) {
      errors.push(`Forbidden template file found: ${fullPath}`);
    }
    if (entry.isDirectory()) {
      scanDir(fullPath);
    } else if (/\.(js|jsx|ts|tsx|css|html|svg|json|md)$/i.test(entry.name)) {
      checkFileContent(fullPath);
    }
  }
}

// 1. Check directories and target files
for (const dir of targetDirs) {
  scanDir(dir);
}
for (const file of targetFiles) {
  if (fs.existsSync(file)) {
    checkFileContent(file);
  }
}

// 2. Check CONTACT_EMAIL in src/config.js
const configFile = path.join(rootDir, 'src', 'config.js');
if (!fs.existsSync(configFile)) {
  errors.push(`Missing required file: ${configFile}`);
} else {
  const configContent = fs.readFileSync(configFile, 'utf-8');
  if (!configContent.includes('CONTACT_EMAIL')) {
    errors.push(`${configFile} is missing required CONTACT_EMAIL export`);
  }
}

if (errors.length > 0) {
  console.error('\x1b[31mCheck failed with the following violations:\x1b[0m');
  for (const err of errors) {
    console.error(`  - ${err}`);
  }
  process.exit(1);
} else {
  console.log('\x1b[32mAll design and constraint checks passed successfully.\x1b[0m');
  process.exit(0);
}

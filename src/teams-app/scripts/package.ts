import { existsSync, mkdirSync, readdirSync, readFileSync } from 'fs';
import { join, resolve } from 'path';
import AdmZip from 'adm-zip';

const appPackageDir = resolve(__dirname, '..', 'appPackage');
const manifestPath = join(appPackageDir, 'manifest.json');
const iconsDir = join(appPackageDir, 'icons');

if (!existsSync(manifestPath)) {
  throw new Error('manifest.json not found in appPackage directory.');
}

if (!existsSync(iconsDir)) {
  throw new Error('icons directory not found in appPackage.');
}

const zip = new AdmZip();
zip.addFile('manifest.json', readFileSync(manifestPath));

const icons = readdirSync(iconsDir).filter((file) => file.endsWith('.png'));

if (icons.length === 0) {
  throw new Error('No PNG icons found in appPackage/icons.');
}

for (const icon of icons) {
  const filePath = join(iconsDir, icon);
  zip.addFile(`icons/${icon}`, readFileSync(filePath));
}

const outputDir = join(appPackageDir, 'dist');
if (!existsSync(outputDir)) {
  mkdirSync(outputDir);
}

const outputPath = join(outputDir, `teams-rag-app-${Date.now()}.zip`);
zip.writeZip(outputPath);

// eslint-disable-next-line no-console
console.log(`App package created at ${outputPath}`);

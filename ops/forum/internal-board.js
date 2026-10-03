'use strict';
// Compatibility entry point for the same tier policy; dry-run by default.
require('./tiered-access').main().then(() => process.exit(0)).catch(error => {
  console.error(error); process.exit(1);
});

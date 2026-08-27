// Conventional Commits enforcement (optional — see CONTRIBUTING.md).
//
// This config is inert until you opt in:
//   pnpm add -D @commitlint/cli @commitlint/config-conventional
//   # then wire a commit-msg hook that runs: pnpm exec commitlint --edit "$1"
//
// Left CommonJS on purpose: the repo root has no "type": "module", so a plain
// module.exports is what Node resolves here.
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // The types we actually use (matches CONTRIBUTING.md and the git history).
    'type-enum': [
      2,
      'always',
      [
        'feat',
        'fix',
        'docs',
        'chore',
        'refactor',
        'test',
        'style',
        'perf',
        'build',
        'ci',
      ],
    ],
    'subject-case': [0], // allow any case in the summary (e.g. proper nouns)
  },
};

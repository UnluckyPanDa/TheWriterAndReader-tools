const token = document.querySelector('meta[name="twr-token"]').content;
const initialWorkspace = document.querySelector('meta[name="twr-workspace"]').content;
const authUrl = document.querySelector('meta[name="twr-auth-url"]').content.replace(/\/$/, '');
const authAnonKey = document.querySelector('meta[name="twr-auth-anon-key"]').content;
const authRequired = document.querySelector('meta[name="twr-auth-required"]').content === 'true';
const elements = {
  workspace: document.getElementById('workspacePath'), workspaceMessage: document.getElementById('workspaceMessage'), chooseWorkspace: document.getElementById('chooseWorkspace'), workspaceHistory: document.getElementById('workspaceHistory'),
  storySelect: document.getElementById('storySelect'), storyList: document.getElementById('storyList'), seriesList: document.getElementById('seriesList'),
  storyCount: document.getElementById('storyCount'), seriesCount: document.getElementById('seriesCount'), chapter: document.getElementById('chapter'), config: document.getElementById('configPath'),
  selectedTitle: document.getElementById('selectedTitle'), selectedMeta: document.getElementById('selectedMeta'), preview: document.getElementById('previewLink'),
  readerTitle: document.getElementById('readerTitle'), readerSource: document.getElementById('readerSource'), readerContent: document.getElementById('readerContent'), readerChapter: document.getElementById('readerChapter'),
  wikiList: document.getElementById('wikiList'), wikiCount: document.getElementById('wikiCount'), wikiPage: document.getElementById('wikiPage'), wikiTitle: document.getElementById('wikiTitle'), wikiContent: document.getElementById('wikiContent'),
  storylineFile: document.getElementById('storylineFile'), storylineContent: document.getElementById('storylineContent'), relationsContent: document.getElementById('relationsContent'),
  activity: document.getElementById('activity'), busy: document.getElementById('busy'), busyText: document.getElementById('busyText'), themeToggle: document.getElementById('themeToggle'), languageSelect: document.getElementById('languageSelect'),
  authGate: document.getElementById('authGate'), authForm: document.getElementById('authForm'), authEmail: document.getElementById('authEmail'), authPassword: document.getElementById('authPassword'), authSubmit: document.getElementById('authSubmit'), authSignup: document.getElementById('authSignup'), authReset: document.getElementById('authReset'), authMessage: document.getElementById('authMessage'), authUser: document.getElementById('authUser'), signOut: document.getElementById('signOut'),
};

let workspaceState = null;
let readerState = null;
let running = false;
let authSession = null;
let userSettings = { theme: 'dark', language: 'en', workspace_history: [] };

const UI_STRINGS = {
  en: {
    controlRoom: 'Control Room', localSession: 'Local session', light: 'Light', dark: 'Dark',
    reader: 'Reader', writing: 'Writing', review: 'Review', storyline: 'Storyline', relations: 'Relations', publishing: 'Publishing', system: 'System',
    workspace: 'Workspace', chooseFolder: 'Choose folder', loadWorkspace: 'Load workspace', recentWorkspaces: 'Recent workspaces', workspaceMessage: 'Choose an external story workspace.',
    stories: 'Stories', series: 'Series', session: 'Session', story: 'Story', selectStory: 'Select a story', chapter: 'Chapter', config: 'Config', optional: 'optional', defaultConfig: 'Default local config',
    selectedStory: 'Selected story', chooseWorkspace: 'Choose a workspace', selectedMeta: 'Load a workspace to inspect its stories and invoke tools.', openPlot: 'Open 3D plot',
    storyReader: 'Story reader', readerDescription: 'Read the selected chapter and jump into canon or planning pages through wiki-style links.', noChapter: 'No chapter selected', loadStory: 'Load a story to begin reading.', writePack: 'Write pack', draftChapter: 'Draft chapter', reviewPack: 'Review pack', runReview: 'Run review', planStoryline: 'Plan storyline →', editRelations: 'Edit relations →', storyWiki: 'Story wiki', noStory: 'No story loaded', backWiki: '← Back to wiki',
    writingTools: 'Writing tools', writingDescription: 'Build context and invoke the configured writer against the selected chapter.', buildWritePack: 'Build write pack', writePackDescription: 'Assemble canon, handoff, plan, and relationship context.', generateDraft: 'Generate draft', draftDescription: 'Run the local writer model for the selected chapter.',
    reviewTools: 'Review tools', reviewDescription: 'Prepare review context, run configured reviewers, and record human comments.', buildReviewPack: 'Build review pack', reviewPackDescription: 'Prepare draft, canon, reveal lock, and reviewer context.', runConfiguredReview: 'Run configured review', reviewRunDescription: 'Invoke the review gate and save evidence in the story workspace.', addReviewComment: 'Add user review comment', author: 'Author', yourName: 'Your name', location: 'Location', sceneLocation: 'Chapter, scene, or paragraph', comment: 'Comment', commentPlaceholder: 'Record a reader observation, issue, or decision…', saveReviewComment: 'Save review comment',
    storylineDescription: "Edit the selected story's planning files directly from the reader workflow.", masterOutline: 'Master outline', partOutline: 'Part outline', chapterPlan: 'Chapter plan', revealLock: 'Reveal lock', loadPage: 'Load page', saveStoryline: 'Save storyline', storylinePlaceholder: 'Select a story and load a storyline page.', storyLanguage: 'Story language',
    relationsDescription: 'Maintain the validated relationship graph and open its interactive 3D view.', initializeGraph: 'Initialize graph', buildPlot: 'Build 3D plot', loadGraph: 'Load graph', saveGraph: 'Save graph', graphPlaceholder: 'Load the relationship graph YAML.',
    publishingDescription: "Check the selected chapter's accepted source and review gate before publishing.", buildPublishPack: 'Build publish pack', publishDescription: 'Prepare publish context and source warnings.',
    systemHeading: 'System and setup', systemDescription: 'Manage workspace scaffolds and validate local configuration.', userSettings: 'User settings', language: 'Language', initializeWorkspace: 'Initialize workspace', workspaceId: 'Workspace ID', myWorkspace: 'my-workspace', initialize: 'Initialize', addStory: 'Add story', storyId: 'Story ID', storyIdPlaceholder: 'story-1', title: 'Title', storyTitle: 'Story title', addSeries: 'Add series', seriesId: 'Series ID', seriesPlaceholder: 'series-1', seriesTitle: 'Series title', validateConfig: 'Validate config', showConfigPath: 'Show config path', runDoctor: 'Run doctor', importExport: 'Import or export configuration', destination: 'Destination', exportPlaceholder: '/path/to/config-export.yaml', mode: 'Mode', noSecrets: 'No secrets', includeSecrets: 'Include secrets', exportConfig: 'Export config', source: 'Source', configPlaceholder: '/path/to/config.yaml', target: 'Target', defaultConfigPath: 'Default config path', importConfig: 'Import config',
    activity: 'Activity', clear: 'Clear', activityEmpty: 'Tool results will appear here.', toolRunning: 'Tool running', pleaseWait: 'Please wait…',
    authTitle: 'Sign in to Control Room', authDescription: 'Use your account to access the local TWR tools through this external session.', email: 'Email', password: 'Password', signIn: 'Sign in', createAccount: 'Create account', forgotPassword: 'Forgot password?', signOut: 'Sign out', loginRequired: 'Login required.', checkEmail: 'Check your email to finish creating the account.', signedInAs: 'Signed in as', authUnavailable: 'Authentication is not configured on this server.',
    previousWorkspaces: 'Previous workspaces', workspaceRequired: 'Enter a workspace path.', loadingWorkspace: 'Loading workspace…', openingPicker: 'Opening folder picker…', folderCancelled: 'Folder selection cancelled.', folderSelected: 'Folder selected. Click Load workspace.', noStories: 'No stories yet', noSeries: 'No series yet', noWorkspace: 'No workspace loaded', chooseWorkspaceToRead: 'Load a workspace to begin reading.', noChapterText: 'No chapter text found.', noWiki: 'No wiki pages found', selectWorkspaceStory: 'Select a workspace and story first.',
    actionWritePack: 'write pack', actionWriteDraft: 'generate draft', actionReviewPack: 'review pack', actionReviewRun: 'run configured review', actionPublishPack: 'build publish pack', actionRelationInit: 'initialize graph', actionRelationBuild: 'build 3D plot', actionStorylineSave: 'save storyline', actionGraphSave: 'save graph', actionComment: 'save review comment', actionWorkspaceInit: 'initialize workspace', actionStoryAdd: 'add story', actionSeriesAdd: 'add series', actionConfigValidate: 'validate config', actionConfigPath: 'show config path', actionDoctor: 'run doctor',
  },
  'zh-Hant': {
    controlRoom: '控制室', localSession: '本機工作階段', light: '淺色', dark: '深色',
    reader: '閱讀', writing: '寫作', review: '審閱', storyline: '故事線', relations: '關係', publishing: '發佈', system: '系統',
    workspace: '工作區', chooseFolder: '選擇資料夾', loadWorkspace: '載入工作區', recentWorkspaces: '最近使用的工作區', workspaceMessage: '選擇外部故事工作區。',
    stories: '故事', series: '系列', session: '工作階段', story: '故事', selectStory: '選擇故事', chapter: '章節', config: '設定', optional: '可選', defaultConfig: '預設本機設定',
    selectedStory: '已選故事', chooseWorkspace: '選擇工作區', selectedMeta: '載入工作區以查看故事並使用工具。', openPlot: '開啟 3D 圖',
    storyReader: '故事閱讀器', readerDescription: '閱讀選定章節，並透過 Wiki 連結跳轉至正典或規劃頁面。', noChapter: '尚未選擇章節', loadStory: '載入故事後開始閱讀。', writePack: '寫作資料包', draftChapter: '草擬章節', reviewPack: '審閱資料包', runReview: '執行審閱', planStoryline: '規劃故事線 →', editRelations: '編輯關係 →', storyWiki: '故事 Wiki', noStory: '尚未載入故事', backWiki: '← 返回 Wiki',
    writingTools: '寫作工具', writingDescription: '建立上下文，並對選定章節呼叫已設定的寫作者。', buildWritePack: '建立寫作資料包', writePackDescription: '整理正典、交接、計畫與關係上下文。', generateDraft: '產生草稿', draftDescription: '對選定章節執行本機寫作模型。',
    reviewTools: '審閱工具', reviewDescription: '準備審閱上下文、執行已設定的審閱者，並記錄人工意見。', buildReviewPack: '建立審閱資料包', reviewPackDescription: '準備草稿、正典、揭露鎖定與審閱者上下文。', runConfiguredReview: '執行已設定審閱', reviewRunDescription: '呼叫審閱閘門並將證據儲存至故事工作區。', addReviewComment: '新增使用者審閱意見', author: '作者', yourName: '你的名稱', location: '位置', sceneLocation: '章節、場景或段落', comment: '意見', commentPlaceholder: '記錄讀者觀察、問題或決定……', saveReviewComment: '儲存審閱意見',
    storylineDescription: '直接從閱讀工作流程編輯選定故事的規劃檔案。', masterOutline: '總綱', partOutline: '分部大綱', chapterPlan: '章節計畫', revealLock: '揭露鎖定', loadPage: '載入頁面', saveStoryline: '儲存故事線', storylinePlaceholder: '選擇故事並載入故事線頁面。', storyLanguage: '故事語言',
    relationsDescription: '維護已驗證的關係圖，並開啟互動式 3D 檢視。', initializeGraph: '初始化圖', buildPlot: '建立 3D 圖', loadGraph: '載入圖', saveGraph: '儲存圖', graphPlaceholder: '載入關係圖 YAML。',
    publishingDescription: '發佈前檢查選定章節的已接受來源與審閱閘門。', buildPublishPack: '建立發佈資料包', publishDescription: '準備發佈上下文與來源警告。',
    systemHeading: '系統與設定', systemDescription: '管理工作區範本並驗證本機設定。', userSettings: '使用者設定', language: '介面語言', initializeWorkspace: '初始化工作區', workspaceId: '工作區 ID', myWorkspace: 'my-workspace', initialize: '初始化', addStory: '新增故事', storyId: '故事 ID', storyIdPlaceholder: 'story-1', title: '標題', storyTitle: '故事標題', addSeries: '新增系列', seriesId: '系列 ID', seriesPlaceholder: 'series-1', seriesTitle: '系列標題', validateConfig: '驗證設定', showConfigPath: '顯示設定路徑', runDoctor: '執行診斷', importExport: '匯入或匯出設定', destination: '目的地', exportPlaceholder: '/path/to/config-export.yaml', mode: '模式', noSecrets: '不含密鑰', includeSecrets: '包含密鑰', exportConfig: '匯出設定', source: '來源', configPlaceholder: '/path/to/config.yaml', target: '目標', defaultConfigPath: '預設設定路徑', importConfig: '匯入設定',
    activity: '活動記錄', clear: '清除', activityEmpty: '工具結果會顯示在這裡。', toolRunning: '工具執行中', pleaseWait: '請稍候……',
    authTitle: '登入控制室', authDescription: '使用你的帳號，透過這個外部工作階段存取本機 TWR 工具。', email: '電子郵件', password: '密碼', signIn: '登入', createAccount: '建立帳號', forgotPassword: '忘記密碼？', signOut: '登出', loginRequired: '需要登入。', checkEmail: '請查看電子郵件以完成建立帳號。', signedInAs: '登入身分', authUnavailable: '此伺服器尚未設定驗證。',
    previousWorkspaces: '最近工作區', workspaceRequired: '請輸入工作區路徑。', loadingWorkspace: '正在載入工作區……', openingPicker: '正在開啟資料夾選擇器……', folderCancelled: '已取消選擇資料夾。', folderSelected: '已選擇資料夾。請按「載入工作區」。', noStories: '尚無故事', noSeries: '尚無系列', noWorkspace: '尚未載入工作區', chooseWorkspaceToRead: '載入工作區後開始閱讀。', noChapterText: '找不到章節文字。', noWiki: '找不到 Wiki 頁面', selectWorkspaceStory: '請先選擇工作區與故事。',
    actionWritePack: '寫作資料包', actionWriteDraft: '產生草稿', actionReviewPack: '審閱資料包', actionReviewRun: '執行已設定審閱', actionPublishPack: '建立發佈資料包', actionRelationInit: '初始化圖', actionRelationBuild: '建立 3D 圖', actionStorylineSave: '儲存故事線', actionGraphSave: '儲存圖', actionComment: '儲存審閱意見', actionWorkspaceInit: '初始化工作區', actionStoryAdd: '新增故事', actionSeriesAdd: '新增系列', actionConfigValidate: '驗證設定', actionConfigPath: '顯示設定路徑', actionDoctor: '執行診斷',
  },
};

function t(key) { return UI_STRINGS[userSettings.language]?.[key] || UI_STRINGS.en[key] || key; }

const ACTION_LABELS = {
  write_pack: 'actionWritePack', write_draft: 'actionWriteDraft', review_pack: 'actionReviewPack', review_run: 'actionReviewRun', publish_pack: 'actionPublishPack',
  relation_plot_init: 'actionRelationInit', relation_plot_build: 'actionRelationBuild', storyline_save: 'actionStorylineSave', relationship_graph_save: 'actionGraphSave',
  review_comment_add: 'actionComment', workspace_init: 'actionWorkspaceInit', story_add: 'actionStoryAdd', series_add: 'actionSeriesAdd', config_validate: 'actionConfigValidate', config_path: 'actionConfigPath', doctor: 'actionDoctor',
};

function actionLabel(action) { return t(ACTION_LABELS[action] || action); }

function setText(selector, key) {
  const element = document.querySelector(selector);
  if (element) element.textContent = t(key);
}

function setLabel(selector, key) {
  const element = document.querySelector(selector);
  if (!element) return;
  const textNode = [...element.childNodes].find(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
  if (textNode) textNode.textContent = `${t(key)} `;
}

function setPlaceholder(selector, key) {
  const element = document.querySelector(selector);
  if (element) element.placeholder = t(key);
}

function applyLanguage() {
  document.documentElement.lang = userSettings.language;
  setText('.topbar h1', 'controlRoom');
  setText('#authTitle', 'authTitle'); setText('#authDescription', 'authDescription'); setLabel('#authForm label:nth-of-type(1)', 'email'); setLabel('#authForm label:nth-of-type(2)', 'password'); setText('#authSubmit', 'signIn'); setText('#authSignup', 'createAccount'); setText('#authReset', 'forgotPassword'); setText('#signOut', 'signOut');
  const badge = document.querySelector('.local-badge');
  if (badge) badge.innerHTML = `<span></span>${t('localSession')}`;
  document.querySelectorAll('.tool-tabs [data-section]').forEach(tab => { tab.textContent = t(tab.dataset.section); });
  setLabel('.workspace-bar > label', 'workspace'); setText('#chooseWorkspace', 'chooseFolder'); setText('#loadWorkspace', 'loadWorkspace');
  setLabel('.workspace-history label', 'recentWorkspaces');
  setText('.side-section:nth-of-type(1) h2', 'stories'); setText('.side-section:nth-of-type(2) h2', 'series'); setText('.side-section.compact h2', 'session');
  setLabel('.compact label:nth-of-type(1)', 'story'); setLabel('.compact label:nth-of-type(2)', 'chapter'); setLabel('.compact label:nth-of-type(3)', 'config'); setText('.compact .optional', 'optional');
  setPlaceholder('#workspacePath', 'workspace'); setPlaceholder('#configPath', 'defaultConfig');
  setText('.hero-card .eyebrow', 'selectedStory'); setText('#previewLink', 'openPlot');
  setText('#reader .tool-heading h2', 'storyReader'); setText('#reader .tool-heading > p', 'readerDescription');
  setText('#reader .reader-actions button[data-action="write_pack"]', 'writePack'); setText('#reader .reader-actions button[data-action="write_draft"]', 'draftChapter'); setText('#reader .reader-actions button[data-action="review_pack"]', 'reviewPack'); setText('#reader .reader-actions button[data-action="review_run"]', 'runReview');
  setText('[data-section-link="storyline"]', 'planStoryline'); setText('[data-section-link="relations"]', 'editRelations'); setText('.wiki-pane h3', 'storyWiki'); setText('#closeWiki', 'backWiki');
  setText('#writing .tool-heading h2', 'writingTools'); setText('#writing .tool-heading > p', 'writingDescription'); setText('#writing .action-card:nth-of-type(1) strong', 'buildWritePack'); setText('#writing .action-card:nth-of-type(1) small', 'writePackDescription'); setText('#writing .action-card:nth-of-type(2) strong', 'generateDraft'); setText('#writing .action-card:nth-of-type(2) small', 'draftDescription');
  setText('#review .tool-heading h2', 'reviewTools'); setText('#review .tool-heading > p', 'reviewDescription'); setText('#review .action-card:nth-of-type(1) strong', 'buildReviewPack'); setText('#review .action-card:nth-of-type(1) small', 'reviewPackDescription'); setText('#review .action-card:nth-of-type(2) strong', 'runConfiguredReview'); setText('#review .action-card:nth-of-type(2) small', 'reviewRunDescription'); setText('#commentForm h3', 'addReviewComment'); setLabel('#commentForm .form-row label:nth-of-type(1)', 'author'); setLabel('#commentForm .form-row label:nth-of-type(2)', 'location'); setLabel('#commentForm > label', 'comment'); setPlaceholder('#commentForm input[name="author"]', 'yourName'); setPlaceholder('#commentForm input[name="location"]', 'sceneLocation'); setPlaceholder('#commentForm textarea', 'commentPlaceholder'); setText('#commentForm button', 'saveReviewComment');
  setText('#storyline .tool-heading h2', 'storyline'); setText('#storyline .tool-heading > p', 'storylineDescription'); setText('#storylineFile option[value="master_outline.md"]', 'masterOutline'); setText('#storylineFile option[value="part_outline.md"]', 'partOutline'); setText('#storylineFile option[value="chapter_plan.md"]', 'chapterPlan'); setText('#storylineFile option[value="reveal_lock.md"]', 'revealLock'); setText('#loadStoryline', 'loadPage'); setText('#saveStoryline', 'saveStoryline'); setPlaceholder('#storylineContent', 'storylinePlaceholder');
  setText('#relations .tool-heading h2', 'relations'); setText('#relations .tool-heading > p', 'relationsDescription'); setText('#relations button[data-action="relation_plot_init"]', 'initializeGraph'); setText('#relations button[data-action="relation_plot_build"]', 'buildPlot'); setText('#loadRelations', 'loadGraph'); setText('#saveRelations', 'saveGraph'); setPlaceholder('#relationsContent', 'graphPlaceholder');
  setText('#publishing .tool-heading h2', 'publishing'); setText('#publishing .tool-heading > p', 'publishingDescription'); setText('#publishing .action-card strong', 'buildPublishPack'); setText('#publishing .action-card small', 'publishDescription');
  setText('#system .tool-heading h2', 'systemHeading'); setText('#system .tool-heading > p', 'systemDescription'); setText('.user-settings h3', 'userSettings'); setLabel('.user-settings label', 'language'); setText('#system .card-grid form:nth-of-type(1) h3', 'initializeWorkspace'); setText('#system .card-grid form:nth-of-type(2) h3', 'addStory'); setText('#system .card-grid form:nth-of-type(3) h3', 'addSeries');
  setLabel('#system .card-grid form:nth-of-type(1) label', 'workspaceId'); setLabel('#system .card-grid form:nth-of-type(2) label:nth-of-type(1)', 'storyId'); setLabel('#system .card-grid form:nth-of-type(2) label:nth-of-type(2)', 'title'); setLabel('#system .card-grid form:nth-of-type(2) label:nth-of-type(3)', 'storyLanguage'); setLabel('#system .card-grid form:nth-of-type(3) label:nth-of-type(1)', 'seriesId'); setLabel('#system .card-grid form:nth-of-type(3) label:nth-of-type(2)', 'title');
  setPlaceholder('#system .card-grid form:nth-of-type(1) input', 'myWorkspace'); setPlaceholder('#system .card-grid form:nth-of-type(2) input[name="story"]', 'storyIdPlaceholder'); setPlaceholder('#system .card-grid form:nth-of-type(2) input[name="title"]', 'storyTitle'); setPlaceholder('#system .card-grid form:nth-of-type(3) input[name="series"]', 'seriesPlaceholder'); setPlaceholder('#system .card-grid form:nth-of-type(3) input[name="title"]', 'seriesTitle');
  document.querySelectorAll('#system .card-grid form button').forEach(button => { button.textContent = t('initialize'); });
  setText('#system .system-actions button[data-action="config_validate"]', 'validateConfig'); setText('#system .system-actions button[data-action="config_path"]', 'showConfigPath'); setText('#system .system-actions button[data-action="doctor"]', 'runDoctor'); setText('.config-tools summary', 'importExport'); setLabel('.config-tools form:nth-of-type(1) label:nth-of-type(1)', 'destination'); setLabel('.config-tools form:nth-of-type(1) label:nth-of-type(2)', 'mode'); setText('.config-tools form:nth-of-type(1) option[value="no-secrets"]', 'noSecrets'); setText('.config-tools form:nth-of-type(1) option[value="full-with-secrets"]', 'includeSecrets'); setText('.config-tools form:nth-of-type(1) button', 'exportConfig'); setLabel('.config-tools form:nth-of-type(2) label:nth-of-type(1)', 'source'); setLabel('.config-tools form:nth-of-type(2) label:nth-of-type(2)', 'target'); setText('.config-tools form:nth-of-type(2) .optional', 'optional'); setText('.config-tools form:nth-of-type(2) button', 'importConfig'); setPlaceholder('.config-tools form:nth-of-type(1) input[name="output"]', 'exportPlaceholder'); setPlaceholder('.config-tools form:nth-of-type(2) input[name="input"]', 'configPlaceholder'); setPlaceholder('.config-tools form:nth-of-type(2) input[name="target"]', 'defaultConfigPath');
  setText('.activity-section h2', 'activity'); setText('#clearActivity', 'clear'); setText('#busy strong', 'toolRunning'); if (!running) setText('#busyText', 'pleaseWait');
  if (elements.languageSelect) elements.languageSelect.value = userSettings.language;
  elements.themeToggle.innerHTML = document.body.dataset.theme === 'light' ? `☾ <span>${t('dark')}</span>` : `☼ <span>${t('light')}</span>`;
  renderWorkspaceHistory();
  if (workspaceState) updateSelectedStory(); else { setText('#selectedTitle', 'chooseWorkspace'); setText('#selectedMeta', 'selectedMeta'); }
  if (readerState) renderReader(); else { setText('#readerTitle', 'noChapter'); setText('#readerContent', 'loadStory'); setText('#wikiList', 'noStory'); }
  if (elements.workspaceMessage && !workspaceState) setWorkspaceMessage(t('workspaceMessage'));
  if (elements.activity.classList.contains('empty')) elements.activity.textContent = t('activityEmpty');
}

async function request(url, options = {}, retry = true) {
  const response = await fetch(url, { ...options, headers: { ...requestHeaders(), ...(options.headers || {}) } });
  const data = await response.json();
  if (response.status === 401 && authRequired) {
    if (retry && authSession?.refresh_token) {
      try {
        const refreshed = await authRequest('token?grant_type=refresh_token', { refresh_token: authSession.refresh_token });
        setAuthSession({ ...refreshed, user: authSession.user });
        return request(url, options, false);
      } catch (_) {
        setAuthSession(null);
      }
    } else {
      setAuthSession(null);
    }
  }
  if (!response.ok || data.ok === false) throw new Error(data.error || data.output || `Request failed (${response.status})`);
  return data;
}

function requestHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (authRequired && authSession?.access_token) headers.Authorization = `Bearer ${authSession.access_token}`;
  else if (token) headers['X-TWR-Token'] = token;
  return headers;
}

async function authRequest(path, body, method = 'POST') {
  if (!authUrl || !authAnonKey) throw new Error(t('authUnavailable'));
  const headers = { apikey: authAnonKey, 'Content-Type': 'application/json' };
  if (authSession?.access_token) headers.Authorization = `Bearer ${authSession.access_token}`;
  const response = await fetch(`${authUrl}/auth/v1/${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.msg || data.error_description || data.message || t('loginRequired'));
  return data;
}

function setAuthMessage(message, error = false) {
  if (!elements.authMessage) return;
  elements.authMessage.textContent = message;
  elements.authMessage.style.color = error ? 'var(--danger)' : '';
}

function setAuthSession(session) {
  authSession = session;
  if (session) localStorage.setItem('twr.auth.session', JSON.stringify(session));
  else localStorage.removeItem('twr.auth.session');
  const locked = authRequired && !session;
  elements.authGate.classList.toggle('hidden', !locked);
  document.body.classList.toggle('auth-locked', locked);
  elements.authUser.classList.toggle('hidden', !session);
  elements.signOut.classList.toggle('hidden', !session);
  if (session) {
    const identity = session.user?.email || session.user?.id || '';
    elements.authUser.textContent = `${t('signedInAs')} ${identity}`;
    setAuthMessage('');
  }
}

async function signIn() {
  const data = await authRequest('token?grant_type=password', { email: elements.authEmail.value.trim(), password: elements.authPassword.value });
  if (!data.access_token) throw new Error(t('loginRequired'));
  setAuthSession(data);
  await initialiseUserSettings();
}

async function signUp() {
  const data = await authRequest('signup', { email: elements.authEmail.value.trim(), password: elements.authPassword.value });
  if (data.access_token) {
    setAuthSession(data);
    await initialiseUserSettings();
  } else {
    setAuthMessage(t('checkEmail'));
  }
}

async function resetPassword() {
  await authRequest('recover', { email: elements.authEmail.value.trim() });
  setAuthMessage(t('checkEmail'));
}

async function initialiseAuth() {
  if (!authRequired) {
    setAuthSession(null);
    await initialiseUserSettings();
    return;
  }
  const stored = JSON.parse(localStorage.getItem('twr.auth.session') || 'null');
  if (stored?.access_token) {
    authSession = stored;
    try {
      const identity = await request('/api/auth/me');
      setAuthSession({ ...stored, user: identity.user });
      await initialiseUserSettings();
      return;
    } catch (_) {
      setAuthSession(null);
    }
  }
  setAuthSession(null);
  setAuthMessage(t('loginRequired'));
}

async function saveUserSettings(changes) {
  userSettings = { ...userSettings, ...changes };
  localStorage.setItem('twr.theme', userSettings.theme);
  localStorage.setItem('twr.language', userSettings.language);
  if (userSettings.workspace_history[0]) localStorage.setItem('twr.workspace', userSettings.workspace_history[0]);
  try {
    const saved = await request('/api/settings', { method: 'POST', body: JSON.stringify(userSettings) });
    const { ok: _ok, ...savedSettings } = saved;
    userSettings = { ...userSettings, ...savedSettings };
  } catch (_) {
    // Browser storage remains a fallback when the local settings file is unavailable.
  }
  renderWorkspaceHistory();
}

function renderWorkspaceHistory() {
  const current = elements.workspaceHistory.value;
  elements.workspaceHistory.innerHTML = `<option value="">${t('previousWorkspaces')}</option>`;
  userSettings.workspace_history.forEach(path => elements.workspaceHistory.add(new Option(path, path)));
  elements.workspaceHistory.value = userSettings.workspace_history.includes(current) ? current : '';
}

async function rememberWorkspace(path) {
  const history = [path, ...userSettings.workspace_history.filter(item => item !== path)].slice(0, 12);
  await saveUserSettings({ workspace_history: history });
}

async function loadWorkspace() {
  const path = elements.workspace.value.trim();
  if (!path) return setWorkspaceMessage(t('workspaceRequired'), true);
  setBusy(true, t('loadingWorkspace'));
  try {
    workspaceState = await request(`/api/workspace?path=${encodeURIComponent(path)}`);
    elements.workspace.value = workspaceState.path;
    await rememberWorkspace(workspaceState.path);
    setWorkspaceMessage(`${workspaceState.stories.length} ${t('stories')} · ${workspaceState.series.length} ${t('series')}`);
    renderWorkspace();
  } catch (error) {
    workspaceState = null; renderWorkspace(); setWorkspaceMessage(error.message, true);
  } finally { setBusy(false); }
}

async function chooseWorkspace() {
  setBusy(true, t('openingPicker'));
  try {
    const result = await request('/api/pick-folder', { method: 'POST', body: '{}' });
    if (result.cancelled) {
      setWorkspaceMessage(t('folderCancelled'));
    } else {
      elements.workspace.value = result.path;
      setWorkspaceMessage(t('folderSelected'));
    }
  } catch (error) {
    setWorkspaceMessage(error.message, true);
  } finally { setBusy(false); }
}

function renderWorkspace() {
  const stories = workspaceState?.stories || [];
  const series = workspaceState?.series || [];
  elements.storyCount.textContent = stories.length; elements.seriesCount.textContent = series.length;
  elements.storySelect.innerHTML = `<option value="">${t('selectStory')}</option>`;
  stories.forEach(story => elements.storySelect.add(new Option(story.title, story.id)));
  elements.storyList.innerHTML = ''; elements.storyList.classList.toggle('empty', !stories.length);
  if (!stories.length) elements.storyList.textContent = workspaceState ? t('noStories') : t('noWorkspace');
  stories.forEach(story => {
    const item = document.createElement('button'); item.className = 'entity'; item.dataset.story = story.id;
    const title = document.createElement('strong'); title.textContent = story.title;
    const meta = document.createElement('small'); meta.textContent = `${story.id}${story.has_relation_plot ? ' · 3D plot ready' : ''}`;
    item.append(title, meta); item.onclick = () => selectStory(story.id); elements.storyList.append(item);
  });
  elements.seriesList.innerHTML = ''; elements.seriesList.classList.toggle('empty', !series.length);
  if (!series.length) elements.seriesList.textContent = workspaceState ? t('noSeries') : t('noWorkspace');
  series.forEach(seriesItem => { const item = document.createElement('div'); item.className = 'entity'; item.innerHTML = '<strong></strong><small>Series</small>'; item.querySelector('strong').textContent = seriesItem.id; elements.seriesList.append(item); });
  if (stories.length) selectStory(stories[0].id); else updateSelectedStory();
}

function selectStory(storyId) {
  elements.storySelect.value = storyId;
  document.querySelectorAll('[data-story]').forEach(item => item.classList.toggle('active', item.dataset.story === storyId));
  updateSelectedStory(); loadReader();
}

function updateSelectedStory() {
  const story = workspaceState?.stories.find(item => item.id === elements.storySelect.value);
  elements.selectedTitle.textContent = story?.title || (workspaceState ? 'Choose a story' : 'Choose a workspace');
  elements.selectedMeta.textContent = story ? `${story.id} · ${story.has_relation_graph ? (userSettings.language === 'zh-Hant' ? '已設定關係圖' : 'relationship graph configured') : (userSettings.language === 'zh-Hant' ? '尚未初始化關係圖' : 'relationship graph not initialized')}` : t('selectedMeta');
  setPreviewLink(story?.has_relation_plot ? story.id : null);
}

function relationPreviewUrl(storyId) { return `/relation-plot?workspace=${encodeURIComponent(elements.workspace.value.trim())}&story=${encodeURIComponent(storyId)}${authRequired ? '' : `&token=${encodeURIComponent(token)}`}`; }

function setPreviewLink(storyId) {
  elements.preview.classList.toggle('hidden', !storyId);
  if (!storyId) return;
  if (authRequired) {
    elements.preview.href = '#';
    elements.preview.onclick = event => { event.preventDefault(); openRelationPlot(storyId); };
  } else {
    elements.preview.href = relationPreviewUrl(storyId);
    elements.preview.onclick = null;
  }
}

async function openRelationPlot(storyId) {
  const popup = window.open('about:blank', '_blank');
  if (!popup) return addActivity('relation_plot_build', 'Allow pop-ups to open the relationship plot.', true);
  try {
    const response = await fetch(relationPreviewUrl(storyId), { headers: requestHeaders() });
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    popup.location.href = URL.createObjectURL(await response.blob());
  } catch (error) {
    popup.close();
    addActivity('relation_plot_build', error.message, true);
  }
}

function commonPayload() { return { workspace: elements.workspace.value.trim(), story: elements.storySelect.value, chapter: elements.chapter.value, config: elements.config.value.trim() }; }

async function loadReader(wiki = null) {
  const story = elements.storySelect.value; const workspace = elements.workspace.value.trim();
  if (!story || !workspace) { elements.readerContent.textContent = t('chooseWorkspaceToRead'); elements.readerContent.classList.add('empty'); return; }
  try {
    const query = `/api/reader?workspace=${encodeURIComponent(workspace)}&story=${encodeURIComponent(story)}&chapter=${encodeURIComponent(elements.chapter.value)}${wiki ? `&wiki=${encodeURIComponent(wiki)}` : ''}`;
    readerState = await request(query); renderReader();
  } catch (error) { addActivity('reader', error.message, true); }
}

function renderReader() {
  const data = readerState; const chapter = data.chapter || {};
  elements.readerTitle.textContent = chapter.number ? `${t('chapter')} ${chapter.number}` : t('noChapter');
  elements.readerSource.textContent = chapter.source ? `${chapter.source} source` : '';
  elements.readerContent.classList.toggle('empty', !chapter.content);
  elements.readerContent.innerHTML = chapter.content ? renderWikiText(chapter.content) : t('noChapterText');
  elements.readerContent.querySelectorAll('[data-wiki]').forEach(link => link.onclick = () => openWiki(link.dataset.wiki));
  elements.readerChapter.innerHTML = '';
  (data.chapters.length ? data.chapters : [{ number: Number(elements.chapter.value) }]).forEach(item => elements.readerChapter.add(new Option(`Chapter ${item.number}`, item.number)));
  elements.readerChapter.value = String(chapter.number || elements.chapter.value);
  renderWikiList(data.wiki || []);
  if (data.wiki_page) showWikiPage(data.wiki_page);
  else closeWiki();
}

function renderWikiText(content) {
  const escaped = escapeHtml(content);
  return escaped.replace(/\[\[([a-zA-Z0-9_-]+)\]\]/g, '<button class="wiki-inline" data-wiki="$1">$1</button>').replace(/\n/g, '<br>');
}

function renderWikiList(entries) {
  elements.wikiCount.textContent = entries.length; elements.wikiList.innerHTML = ''; elements.wikiList.classList.toggle('empty', !entries.length); elements.wikiList.classList.remove('hidden'); elements.wikiPage.classList.add('hidden');
  if (!entries.length) elements.wikiList.textContent = t('noWiki');
  entries.forEach(entry => { const button = document.createElement('button'); button.className = 'wiki-link'; button.textContent = entry.title; button.onclick = () => openWiki(entry.key); elements.wikiList.append(button); });
}

async function openWiki(key) {
  try {
    const workspace = elements.workspace.value.trim(); const story = elements.storySelect.value;
    const data = await request(`/api/reader?workspace=${encodeURIComponent(workspace)}&story=${encodeURIComponent(story)}&chapter=${elements.chapter.value}&wiki=${encodeURIComponent(key)}`);
    showWikiPage(data.wiki_page);
  } catch (error) { addActivity('wiki', error.message, true); }
}

function showWikiPage(page) {
  if (!page) return;
  elements.wikiPage.classList.remove('hidden'); elements.wikiList.classList.add('hidden'); elements.wikiTitle.textContent = page.title; elements.wikiContent.textContent = page.content;
}

function closeWiki() { elements.wikiPage.classList.add('hidden'); elements.wikiList.classList.remove('hidden'); }

async function runAction(action, extra = {}) {
  if (running) return;
  const payload = { action, ...commonPayload(), ...extra }; setBusy(true, actionLabel(action));
  try {
    const result = await request('/api/action', { method: 'POST', body: JSON.stringify(payload) }); addActivity(action, result.output, false);
    if (result.workspace) { const selected = payload.story; workspaceState = result.workspace; renderWorkspace(); if (selected && workspaceState.stories.some(item => item.id === selected)) selectStory(selected); }
    if (result.preview) setPreviewLink(payload.story);
    return result;
  } catch (error) { addActivity(action, error.message, true); }
  finally { setBusy(false); }
}

function addActivity(action, output, error) {
  if (elements.activity.classList.contains('empty')) elements.activity.innerHTML = '';
  elements.activity.classList.remove('empty'); const item = document.createElement('article'); item.className = `activity-item${error ? ' error' : ''}`;
  const header = document.createElement('header'); const title = document.createElement('strong'); title.textContent = actionLabel(action); const time = document.createElement('time'); time.textContent = new Date().toLocaleTimeString(); header.append(title, time);
  const body = document.createElement('pre'); body.textContent = typeof output === 'string' ? output : JSON.stringify(output, null, 2); item.append(header, body); elements.activity.prepend(item);
}

function setBusy(value, text = '') { running = value; elements.busy.classList.toggle('hidden', !value); elements.busyText.textContent = text || t('pleaseWait'); document.querySelectorAll('button').forEach(button => button.disabled = value); }
function setWorkspaceMessage(message, error = false) { elements.workspaceMessage.textContent = message; elements.workspaceMessage.style.color = error ? 'var(--danger)' : ''; }
function escapeHtml(value) { const span = document.createElement('span'); span.textContent = value ?? ''; return span.innerHTML; }

function loadWikiEditor(key, textarea) {
  const workspace = elements.workspace.value.trim(); const story = elements.storySelect.value;
  if (!workspace || !story) return addActivity('reader', t('selectWorkspaceStory'), true);
  request(`/api/reader?workspace=${encodeURIComponent(workspace)}&story=${encodeURIComponent(story)}&chapter=${elements.chapter.value}&wiki=${encodeURIComponent(key)}`).then(data => { if (data.wiki_page) textarea.value = data.wiki_page.content; }).catch(error => addActivity('wiki', error.message, true));
}

document.getElementById('loadWorkspace').onclick = loadWorkspace;
elements.chooseWorkspace.onclick = chooseWorkspace;
elements.workspaceHistory.onchange = () => {
  if (!elements.workspaceHistory.value) return;
  elements.workspace.value = elements.workspaceHistory.value;
  loadWorkspace();
};
elements.workspace.addEventListener('keydown', event => { if (event.key === 'Enter') loadWorkspace(); });
elements.storySelect.onchange = () => { selectStory(elements.storySelect.value); };
elements.chapter.onchange = () => { elements.readerChapter.value = elements.chapter.value; loadReader(); };
elements.readerChapter.onchange = () => { elements.chapter.value = elements.readerChapter.value; loadReader(); };
document.getElementById('closeWiki').onclick = closeWiki;
document.getElementById('loadStoryline').onclick = () => loadWikiEditor(elements.storylineFile.value.replace('.md', ''), elements.storylineContent);
document.getElementById('saveStoryline').onclick = () => runAction('storyline_save', { file: elements.storylineFile.value, content: elements.storylineContent.value });
document.getElementById('loadRelations').onclick = () => loadWikiEditor('relationship_graph', elements.relationsContent);
document.getElementById('saveRelations').onclick = () => runAction('relationship_graph_save', { content: elements.relationsContent.value });
document.querySelectorAll('[data-action]').forEach(button => button.onclick = () => runAction(button.dataset.action));
document.querySelectorAll('[data-form-action]').forEach(form => form.onsubmit = event => { event.preventDefault(); runAction(form.dataset.formAction, Object.fromEntries(new FormData(form))); });
document.getElementById('clearActivity').onclick = () => { elements.activity.className = 'activity empty'; elements.activity.textContent = t('activityEmpty'); };

elements.authForm.onsubmit = async event => {
  event.preventDefault();
  setBusy(true, t('signIn'));
  try { await signIn(); } catch (error) { setAuthMessage(error.message, true); }
  finally { setBusy(false); }
};
elements.authSignup.onclick = async () => {
  setBusy(true, t('createAccount'));
  try { await signUp(); } catch (error) { setAuthMessage(error.message, true); }
  finally { setBusy(false); }
};
elements.authReset.onclick = async () => {
  setBusy(true, t('forgotPassword'));
  try { await resetPassword(); } catch (error) { setAuthMessage(error.message, true); }
  finally { setBusy(false); }
};
elements.signOut.onclick = async () => {
  try { if (authSession?.access_token) await authRequest('logout', null); } catch (_) { /* local session is still cleared */ }
  setAuthSession(null);
};

function setTheme(theme, persist = true) {
  document.body.dataset.theme = theme;
  localStorage.setItem('twr.theme', theme);
  elements.themeToggle.innerHTML = theme === 'light' ? `☾ <span>${t('dark')}</span>` : `☼ <span>${t('light')}</span>`;
  if (persist) saveUserSettings({ theme });
}
elements.themeToggle.onclick = () => setTheme(document.body.dataset.theme === 'light' ? 'dark' : 'light');
setTheme(localStorage.getItem('twr.theme') || 'dark', false);
elements.languageSelect.onchange = async () => {
  userSettings.language = elements.languageSelect.value;
  applyLanguage();
  await saveUserSettings({ language: userSettings.language });
};

const toolSections = [...document.querySelectorAll('.tool-section[id]')];
const toolTabs = [...document.querySelectorAll('.tool-tabs [data-section]')];

function activateSection(sectionId, updateHash = true) {
  const section = toolSections.find(item => item.id === sectionId) || toolSections[0];
  toolSections.forEach(item => { item.hidden = item !== section; });
  toolTabs.forEach(tab => {
    const active = tab.dataset.section === section.id;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
  });
  if (updateHash && window.location.hash !== `#${section.id}`) history.replaceState(null, '', `#${section.id}`);
}

toolTabs.forEach(tab => tab.onclick = () => activateSection(tab.dataset.section));
document.querySelectorAll('[data-section-link]').forEach(link => link.onclick = event => {
  event.preventDefault();
  activateSection(link.dataset.sectionLink);
});
const requestedSection = window.location.hash.slice(1);
activateSection(toolSections.some(section => section.id === requestedSection) ? requestedSection : 'reader', false);

async function initialiseUserSettings() {
  const legacyTheme = localStorage.getItem('twr.theme');
  const legacyLanguage = localStorage.getItem('twr.language');
  const legacyWorkspace = localStorage.getItem('twr.workspace');
  try {
    userSettings = { ...userSettings, ...(await request('/api/settings')) };
  } catch (_) {
    userSettings = { ...userSettings, theme: legacyTheme || userSettings.theme, language: legacyLanguage || userSettings.language, workspace_history: legacyWorkspace ? [legacyWorkspace] : [] };
  }
  const migratedHistory = legacyWorkspace && !userSettings.workspace_history.includes(legacyWorkspace)
    ? [legacyWorkspace, ...userSettings.workspace_history].slice(0, 12)
    : userSettings.workspace_history;
  const migratedTheme = legacyTheme && userSettings.theme === 'dark' ? legacyTheme : userSettings.theme;
  const migratedLanguage = legacyLanguage && userSettings.language === 'en' ? legacyLanguage : userSettings.language;
  if (migratedHistory !== userSettings.workspace_history || migratedTheme !== userSettings.theme || migratedLanguage !== userSettings.language) {
    await saveUserSettings({ workspace_history: migratedHistory, theme: migratedTheme, language: migratedLanguage });
  }
  userSettings.language = migratedLanguage;
  setTheme(userSettings.theme, false);
  applyLanguage();
  const remembered = initialWorkspace || userSettings.workspace_history[0] || legacyWorkspace || '';
  if (remembered) { elements.workspace.value = remembered; loadWorkspace(); }
}

initialiseAuth();

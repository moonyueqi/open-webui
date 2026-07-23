<script lang="ts">
	import { getContext, onMount, tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { config, models, settings, user } from '$lib/stores';
	import { updateUserSettings } from '$lib/apis/users';
	import { getModels as _getModels } from '$lib/apis';
	import { goto } from '$app/navigation';

	import Modal from '../common/Modal.svelte';
	import Account from './Settings/Account.svelte';
	import About from './Settings/About.svelte';
	import General from './Settings/General.svelte';
	// 【已注释】界面标签页已禁用
	// import Interface from './Settings/Interface.svelte';
	import Audio from './Settings/Audio.svelte';
	import DataControls from './Settings/DataControls.svelte';
	import Personalization from './Settings/Personalization.svelte';
	import Search from '../icons/Search.svelte';
	import XMark from '../icons/XMark.svelte';
	import Connections from './Settings/Connections.svelte';
	import Integrations from './Settings/Integrations.svelte';
	import DatabaseSettings from '../icons/DatabaseSettings.svelte';
	import SettingsAlt from '../icons/SettingsAlt.svelte';
	import Link from '../icons/Link.svelte';
	import UserCircle from '../icons/UserCircle.svelte';
	import SoundHigh from '../icons/SoundHigh.svelte';
	import InfoCircle from '../icons/InfoCircle.svelte';
	import WrenchAlt from '../icons/WrenchAlt.svelte';
	import Face from '../icons/Face.svelte';
	import AppNotification from '../icons/AppNotification.svelte';
	import UserBadgeCheck from '../icons/UserBadgeCheck.svelte';

	const i18n = getContext('i18n');

	export let show = false;

	$: if (show) {
		addScrollListener();
	} else {
		removeScrollListener();
	}

	interface SettingsTab {
		id: string;
		title: string;
		keywords: string[];
	}

	const allSettings: SettingsTab[] = [
		// 【已注释】通用标签页 - 语言和系统提示词由系统统一配置，不允许用户修改
		// {
		// 	id: 'general',
		// 	title: 'General',
		// 	keywords: [
		// 		'advancedparams', 'advancedparameters', 'advanced params', 'advanced parameters',
		// 		'configuration', 'defaultparameters', 'default parameters', 'defaultsettings',
		// 		'default settings', 'general', 'keepalive', 'keep alive', 'languages',
		// 		'notifications', 'requestmode', 'request mode', 'systemparameters',
		// 		'system parameters', 'systemprompt', 'system prompt', 'systemsettings',
		// 		'system settings', 'theme', 'translate', 'webuisettings', 'webui settings'
		// 	]
		// },
		// 【已注释】界面标签页 - 所有界面设置沿用系统默认，不允许用户修改
		// {
		// 	id: 'interface',
		// 	title: 'Interface',
		// 	keywords: [...]
		// },
		{
			id: 'account',
			title: 'Account',
			keywords: [
				'account preferences',
				'account settings',
				'accountpreferences',
				'accountsettings',
				'api keys',
				'apikeys',
				'change password',
				'changepassword',
				'jwt token',
				'jwttoken',
				'login',
				'new password',
				'newpassword',
				'notification webhook url',
				'notificationwebhookurl',
				'personal settings',
				'personalsettings',
				'privacy settings',
				'privacysettings',
				'profileavatar',
				'profile avatar',
				'profile details',
				'profile image',
				'profile picture',
				'profiledetails',
				'profileimage',
				'profilepicture',
				'security settings',
				'securitysettings',
				'update account',
				'update password',
				'updateaccount',
				'updatepassword',
				'user account',
				'user data',
				'user preferences',
				'user profile',
				'useraccount',
				'userdata',
				'username',
				'userpreferences',
				'userprofile',
				'webhook url',
				'webhookurl'
			]
		},
		{
			id: 'connections',
			title: 'Connections',
			keywords: [
				'addconnection',
				'add connection',
				'manageconnections',
				'manage connections',
				'manage direct connections',
				'managedirectconnections',
				'settings'
			]
		},
		// 【已注释】扩展功能标签页 - 不允许普通用户修改
		// {
		// 	id: 'tools',
		// 	title: 'Integrations',
		// 	keywords: [
		// 		'addconnection',
		// 		'add connection',
		// 		'integrations',
		// 		'managetools',
		// 		'manage tools',
		// 		'manage tool servers',
		// 		'managetoolservers',
		// 		'open terminal',
		// 		'openterminal',
		// 		'terminal',
		// 		'settings'
		// 	]
		// },
		{
			id: 'personalization',
			title: 'Personalization',
			keywords: [
				'account preferences',
				'account settings',
				'accountpreferences',
				'accountsettings',
				'custom settings',
				'customsettings',
				'experimental',
				'memories',
				'memory',
				'personalization',
				'personalize',
				'personal settings',
				'personalsettings',
				'profile',
				'user preferences',
				'userpreferences'
			]
		},
		// 【已注释】语音标签页 - 不允许普通用户修改
		// {
		// 	id: 'audio',
		// 	title: 'Audio',
		// 	keywords: [
		// 		'audio config',
		// 		'audio control',
		// 		'audio features',
		// 		'audio input',
		// 		'audio output',
		// 		'audio playback',
		// 		'audio voice',
		// 		'audioconfig',
		// 		'audiocontrol',
		// 		'audiofeatures',
		// 		'audioinput',
		// 		'audiooutput',
		// 		'audioplayback',
		// 		'audiovoice',
		// 		'auto playback response',
		// 		'autoplaybackresponse',
		// 		'auto transcribe',
		// 		'autotranscribe',
		// 		'instant auto send after voice transcription',
		// 		'instantautosendaftervoicetranscription',
		// 		'language',
		// 		'non local voices',
		// 		'nonlocalvoices',
		// 		'save settings',
		// 		'savesettings',
		// 		'set voice',
		// 		'setvoice',
		// 		'sound settings',
		// 		'soundsettings',
		// 		'speech config',
		// 		'speech mode',
		// 		'speech playback speed',
		// 		'speech rate',
		// 		'speech recognition',
		// 		'speech settings',
		// 		'speech speed',
		// 		'speech synthesis',
		// 		'speech to text engine',
		// 		'speechconfig',
		// 		'speechmode',
		// 		'speechplaybackspeed',
		// 		'speechrate',
		// 		'speechrecognition',
		// 		'speechsettings',
		// 		'speechspeed',
		// 		'speechsynthesis',
		// 		'speechtotextengine',
		// 		'speedch playback rate',
		// 		'speedchplaybackrate',
		// 		'stt settings',
		// 		'sttsettings',
		// 		'text to speech engine',
		// 		'text to speech',
		// 		'textospeechengine',
		// 		'texttospeech',
		// 		'texttospeechvoice',
		// 		'text to speech voice',
		// 		'voice control',
		// 		'voice modes',
		// 		'voice options',
		// 		'voice playback',
		// 		'voice recognition',
		// 		'voice speed',
		// 		'voicecontrol',
		// 		'voicemodes',
		// 		'voiceoptions',
		// 		'voiceplayback',
		// 		'voicerecognition',
		// 		'voicespeed',
		// 		'volume'
		// 	]
		// },
		// 【已注释】数据标签页 - 不允许普通用户修改
		// {
		// 	id: 'data_controls',
		// 	title: 'Data Controls',
		// 	keywords: [
		// 		'archive all chats',
		// 		'archive chats',
		// 		'archiveallchats',
		// 		'archivechats',
		// 		'archived chats',
		// 		'archivedchats',
		// 		'chat activity',
		// 		'chat history',
		// 		'chat settings',
		// 		'chatactivity',
		// 		'chathistory',
		// 		'chatsettings',
		// 		'conversation activity',
		// 		'conversation history',
		// 		'conversationactivity',
		// 		'conversationhistory',
		// 		'conversations',
		// 		'convos',
		// 		'delete all chats',
		// 		'delete chats',
		// 		'deleteallchats',
		// 		'deletechats',
		// 		'export chats',
		// 		'exportchats',
		// 		'import chats',
		// 		'importchats',
		// 		'message activity',
		// 		'message archive',
		// 		'message history',
		// 		'messagearchive',
		// 		'messagehistory'
		// 	]
		// },
		{
			id: 'about',
			title: 'About',
			keywords: [
				'about app',
				'about me',
				'about open webui',
				'about page',
				'about us',
				'aboutapp',
				'aboutme',
				'aboutopenwebui',
				'aboutpage',
				'aboutus',
				'check for updates',
				'checkforupdates',
				'contact',
				'copyright',
				'details',
				'discord',
				'documentation',
				'github',
				'help',
				'information',
				'license',
				'redistributions',
				'release',
				'see whats new',
				'seewhatsnew',
				'settings',
				'software info',
				'softwareinfo',
				'support',
				'terms and conditions',
				'terms of use',
				'termsandconditions',
				'termsofuse',
				'timothy jae ryang baek',
				'timothy j baek',
				'timothyjaeryangbaek',
				'timothyjbaek',
				'twitter',
				'update info',
				'updateinfo',
				'version info',
				'versioninfo'
			]
		}
	];

	let availableSettings = [];
	let filteredSettings = [];

	let search = '';
	let searchDebounceTimeout;

	const getAvailableSettings = () => {
		return allSettings.filter((tab) => {
			if (tab.id === 'connections') {
				return $config?.features?.enable_direct_connections;
			}

			// 【已注释】扩展功能标签页已禁用
			// if (tab.id === 'tools') {
			// 	return (
			// 		$user?.role === 'admin' ||
			// 		($user?.role === 'user' && $user?.permissions?.features?.direct_tool_servers)
			// 	);
			// }

			// 【已注释】界面标签页已禁用
			// if (tab.id === 'interface') {
			// 	return $user?.role === 'admin' || ($user?.permissions?.settings?.interface ?? true);
			// }

			if (tab.id === 'personalization') {
				return (
					$config?.features?.enable_memories &&
					($user?.role === 'admin' || ($user?.permissions?.features?.memories ?? true))
				);
			}

			return true;
		});
	};

	const setFilteredSettings = () => {
		filteredSettings = availableSettings
			.filter((tab) => {
				return (
					search === '' ||
					tab.title.toLowerCase().includes(search.toLowerCase().trim()) ||
					tab.keywords.some((keyword) => keyword.includes(search.toLowerCase().trim()))
				);
			})
			.map((tab) => tab.id);

		if (filteredSettings.length > 0 && !filteredSettings.includes(selectedTab)) {
			selectedTab = filteredSettings[0];
		}
	};

	const searchDebounceHandler = () => {
		if (searchDebounceTimeout) {
			clearTimeout(searchDebounceTimeout);
		}

		searchDebounceTimeout = setTimeout(() => {
			setFilteredSettings();
		}, 100);
	};

	const saveSettings = async (updated) => {
		console.log(updated);
		await settings.set({ ...$settings, ...updated });
		await models.set(await getModels());
		await updateUserSettings(localStorage.token, { ui: $settings });
	};

	const getModels = async () => {
		return await _getModels(
			localStorage.token,
			$config?.features?.enable_direct_connections && ($settings?.directConnections ?? null)
		);
	};

	let selectedTab = 'account';

	// Function to handle sideways scrolling
	const scrollHandler = (event) => {
		const settingsTabsContainer = document.getElementById('settings-tabs-container');
		if (settingsTabsContainer) {
			event.preventDefault(); // Prevent default vertical scrolling
			settingsTabsContainer.scrollLeft += event.deltaY; // Scroll sideways
		}
	};

	const addScrollListener = async () => {
		await tick();
		const settingsTabsContainer = document.getElementById('settings-tabs-container');
		if (settingsTabsContainer) {
			settingsTabsContainer.addEventListener('wheel', scrollHandler);
		}
	};

	const removeScrollListener = async () => {
		await tick();
		const settingsTabsContainer = document.getElementById('settings-tabs-container');
		if (settingsTabsContainer) {
			settingsTabsContainer.removeEventListener('wheel', scrollHandler);
		}
	};

	onMount(() => {
		availableSettings = getAvailableSettings();
		setFilteredSettings();

		config.subscribe((configData) => {
			availableSettings = getAvailableSettings();
			setFilteredSettings();
		});
	});
</script>

<Modal size="sm" bind:show>
	<div class="text-gray-700 dark:text-gray-100">
		<div class="flex items-center justify-between px-6 pt-5 pb-4">
			<div class="flex items-center gap-2.5">
				<div class="p-2 rounded-xl bg-gray-100 dark:bg-gray-800">
					<SettingsAlt strokeWidth="1.5" className="size-5 text-gray-600 dark:text-gray-300" />
				</div>
				<div>
					<div class="text-lg font-semibold tracking-tight">{$i18n.t('Settings')}</div>
					<div class="text-xs text-gray-400 dark:text-gray-500">{$i18n.t('Manage your preferences')}</div>
				</div>
			</div>
			<button
				aria-label={$i18n.t('Close settings modal')}
				class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className="size-4 text-gray-500" />
			</button>
		</div>

		<div class="px-6 pb-1">
			<div
				role="tablist"
				id="settings-tabs-container"
				class="tabs flex flex-row gap-1 overflow-x-auto border-b border-gray-100 dark:border-gray-800"
			>
				{#if filteredSettings.length > 0}
					{#each filteredSettings as tabId (tabId)}
						{#if tabId === 'account'}
							<button
								role="tab"
								aria-controls="tab-account"
								aria-selected={selectedTab === 'account'}
								class="relative px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors
									{selectedTab === 'account'
										? 'text-gray-900 dark:text-white'
										: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'}"
								on:click={() => { selectedTab = 'account'; }}
							>
								<div class="flex items-center gap-2">
									<UserCircle strokeWidth="2" className="size-4" />
									<span>{$i18n.t('Account')}</span>
								</div>
								{#if selectedTab === 'account'}
									<div class="absolute bottom-0 left-0 right-0 h-0.5 bg-gray-900 dark:bg-white rounded-full"></div>
								{/if}
							</button>
						{:else if tabId === 'connections'}
							{#if $user?.role === 'admin' || ($user?.role === 'user' && $config?.features?.enable_direct_connections)}
								<button
									role="tab"
									aria-controls="tab-connections"
									aria-selected={selectedTab === 'connections'}
									class="relative px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors
										{selectedTab === 'connections'
											? 'text-gray-900 dark:text-white'
											: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'}"
									on:click={() => { selectedTab = 'connections'; }}
								>
									<div class="flex items-center gap-2">
										<Link strokeWidth="2" className="size-4" />
										<span>{$i18n.t('Connections')}</span>
									</div>
									{#if selectedTab === 'connections'}
										<div class="absolute bottom-0 left-0 right-0 h-0.5 bg-gray-900 dark:bg-white rounded-full"></div>
									{/if}
								</button>
							{/if}
						{:else if tabId === 'personalization'}
							<button
								role="tab"
								aria-controls="tab-personalization"
								aria-selected={selectedTab === 'personalization'}
								class="relative px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors
									{selectedTab === 'personalization'
										? 'text-gray-900 dark:text-white'
										: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'}"
								on:click={() => { selectedTab = 'personalization'; }}
							>
								<div class="flex items-center gap-2">
									<Face strokeWidth="2" className="size-4" />
									<span>{$i18n.t('Personalization')}</span>
								</div>
								{#if selectedTab === 'personalization'}
									<div class="absolute bottom-0 left-0 right-0 h-0.5 bg-gray-900 dark:bg-white rounded-full"></div>
								{/if}
							</button>
						{:else if tabId === 'about'}
							<button
								role="tab"
								aria-controls="tab-about"
								aria-selected={selectedTab === 'about'}
								class="relative px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors
									{selectedTab === 'about'
										? 'text-gray-900 dark:text-white'
										: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'}"
								on:click={() => { selectedTab = 'about'; }}
							>
								<div class="flex items-center gap-2">
									<InfoCircle strokeWidth="2" className="size-4" />
									<span>{$i18n.t('About')}</span>
								</div>
								{#if selectedTab === 'about'}
									<div class="absolute bottom-0 left-0 right-0 h-0.5 bg-gray-900 dark:bg-white rounded-full"></div>
								{/if}
							</button>
						{/if}
					{/each}
				{/if}

				{#if $user?.role === 'admin'}
					<a
						href="/admin/settings"
						draggable="false"
						class="relative ml-auto px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 select-none"
						on:click={async (e) => {
							e.preventDefault();
							await goto('/admin/settings');
							show = false;
						}}
					>
						<div class="flex items-center gap-2">
							<UserBadgeCheck strokeWidth="2" className="size-4" />
							<span>{$i18n.t('Admin Settings')}</span>
						</div>
					</a>
				{/if}
			</div>
		</div>

		<div class="px-6 pt-4 pb-6 min-h-[24rem] max-h-[28rem] overflow-y-auto">
			{#if selectedTab === 'account'}
				<Account
					{saveSettings}
					saveHandler={() => {
						toast.success($i18n.t('Settings saved successfully!'));
					}}
				/>
			{:else if selectedTab === 'connections'}
				<Connections
					saveSettings={async (updated) => {
						await saveSettings(updated);
						toast.success($i18n.t('Settings saved successfully!'));
					}}
				/>
			{:else if selectedTab === 'personalization'}
				<Personalization
					{saveSettings}
					on:save={async () => {
						toast.success($i18n.t('Settings saved successfully!'));
					}}
				/>
			{:else if selectedTab === 'about'}
				<About />
			{/if}
		</div>
	</div>
</Modal>

<style>
	input::-webkit-outer-spin-button,
	input::-webkit-inner-spin-button {
		/* display: none; <- Crashes Chrome on hover */
		-webkit-appearance: none;
		margin: 0; /* <-- Apparently some margin are still there even though it's hidden */
	}

	.tabs::-webkit-scrollbar {
		display: none; /* for Chrome, Safari and Opera */
	}

	.tabs {
		-ms-overflow-style: none; /* IE and Edge */
		scrollbar-width: none; /* Firefox */
	}

	input[type='number'] {
		appearance: textfield;
		-moz-appearance: textfield; /* Firefox */
	}
</style>

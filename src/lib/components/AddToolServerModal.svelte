<script lang="ts">
	import { v4 as uuidv4 } from 'uuid';

	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	import { toast } from 'svelte-sonner';
	import { getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');

	import { settings } from '$lib/stores';
	import Modal from '$lib/components/common/Modal.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import { getToolServerData } from '$lib/apis';
	import { verifyToolServerConnection, registerOAuthClient } from '$lib/apis/configs';
	import { getToolCategories } from '$lib/apis/tool-categories';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Textarea from './common/Textarea.svelte';

	export let onSubmit: Function = () => {};
	export let onDelete: Function = () => {};

	export let show = false;
	export let edit = false;

	export let direct = false;
	export let connection = null;

	let inputElement = null;

	let type = 'openapi'; // 'openapi', 'mcp'

	let url = '';

	let spec_type = 'url'; // 'url', 'json'
	let spec = ''; // used when spec_type is 'json'
	let path = 'openapi.json';

	let auth_type = 'bearer';
	let key = '';
	let headers = '';

	let functionNameFilterList = '';

	let categoryId = '';
	let categories: any[] = [];

	let id = '';
	let name = '';
	let description = '';

	let oauthClientInfo = null;

	let enable = true;
	let loading = false;
	let verifying = false;
	let showAdvanced = false;

	const registerOAuthClientHandler = async () => {
		if (url === '') {
			toast.error($i18n.t('Please enter a valid URL'));
			return;
		}

		if (id === '') {
			toast.error($i18n.t('Please enter a valid ID'));
			return;
		}

		const res = await registerOAuthClient(
			localStorage.token,
			{
				url: url,
				client_id: id
			},
			'mcp'
		).catch((err) => {
			toast.error($i18n.t('Registration failed'));
			return null;
		});

		if (res) {
			toast.warning(
				$i18n.t(
					'Please save the connection to persist the OAuth client information and do not change the ID'
				)
			);
			toast.success($i18n.t('Registration successful'));

			console.debug('Registration successful', res);
			oauthClientInfo = res?.oauth_client_info ?? null;
		}
	};

	const verifyHandler = async () => {
		if (url === '') {
			toast.error($i18n.t('Please enter a valid URL'));
			return;
		}

		if (['openapi', ''].includes(type)) {
			if (spec_type === 'json' && spec === '') {
				toast.error($i18n.t('Please enter a valid JSON spec'));
				return;
			}

			if (spec_type === 'url' && path === '') {
				toast.error($i18n.t('Please enter a valid path'));
				return;
			}
		}

		if (headers) {
			try {
				let _headers = JSON.parse(headers);
				if (typeof _headers !== 'object' || Array.isArray(_headers)) {
					_headers = null;
					throw new Error('Headers must be a valid JSON object');
				}
				headers = JSON.stringify(_headers, null, 2);
			} catch (error) {
				toast.error($i18n.t('Headers must be a valid JSON object'));
				return;
			}
		}

		verifying = true;
		try {
			if (direct) {
				const res = await getToolServerData(
					auth_type === 'bearer' ? key : localStorage.token,
					path.includes('://') ? path : `${url}${path.startsWith('/') ? '' : '/'}${path}`
				).catch((err) => {
					toast.error($i18n.t('Connection failed'));
				});

				if (res) {
					toast.success($i18n.t('Connection successful'));
					console.debug('Connection successful', res);
				}
			} else {
				const res = await verifyToolServerConnection(localStorage.token, {
					url,
					path,
					type,
					auth_type,
					headers: headers ? JSON.parse(headers) : undefined,
					key,
					config: {
						enable: enable
					},
					info: {
						id,
						name,
						description
					}
				}).catch((err) => {
					toast.error($i18n.t('Connection failed'));
				});

				if (res) {
					toast.success($i18n.t('Connection successful'));
					console.debug('Connection successful', res);
				}
			}
		} finally {
			verifying = false;
		}
	};

	const importHandler = async (e) => {
		const file = e.target.files[0];
		if (!file) return;

		const reader = new FileReader();
		reader.onload = (event) => {
			const json = event.target.result;
			console.log('importHandler', json);

			try {
				let data = JSON.parse(json);
				if (Array.isArray(data)) {
					if (data.length === 0) {
						toast.error($i18n.t('Please select a valid JSON file'));
						return;
					}
					data = data[0];
				}

				if (data.type) type = data.type;
				if (data.url) url = data.url;

				if (data.spec_type) spec_type = data.spec_type;
				if (data.spec) spec = data.spec;
				if (data.path) path = data.path;

				if (data.auth_type) auth_type = data.auth_type;
				if (data.headers) headers = JSON.stringify(data.headers, null, 2);
				if (data.key) key = data.key;

				if (data.info) {
					id = data.info.id ?? '';
					name = data.info.name ?? '';
					description = data.info.description ?? '';
				}

				if (data.config) {
					enable = data.config.enable ?? true;
					categoryId = data.config.category_id ?? '';
				}

				toast.success($i18n.t('Import successful'));
			} catch (error) {
				toast.error($i18n.t('Please select a valid JSON file'));
			}
		};
		reader.readAsText(file);
	};

	const exportHandler = async () => {
		const json = JSON.stringify([
			{
				type,
				url,

				spec_type,
				spec,
				path,

				auth_type,
				headers: headers ? JSON.parse(headers) : undefined,
				key,

				info: {
					id: id,
					name: name,
					description: description
				}
			}
		]);

		const blob = new Blob([json], {
			type: 'application/json'
		});

		saveAs(blob, `tool-server-${id || name || 'export'}.json`);
	};

	const submitHandler = async () => {
		loading = true;

		// remove trailing slash from url for non-MCP connections
		// MCP servers may require a trailing slash; stripping it can cause
		// 301 redirects that lose auth headers (see #21179)
		if (type !== 'mcp') {
			url = url.replace(/\/$/, '');
		}
		if (id.includes(':') || id.includes('|')) {
			toast.error($i18n.t('ID cannot contain ":" or "|" characters'));
			loading = false;
			return;
		}

		if (type === 'mcp' && auth_type === 'oauth_2.1' && !oauthClientInfo) {
			toast.error($i18n.t('Please register the OAuth client'));
			loading = false;
			return;
		}

		if (spec_type === 'json') {
			try {
				const specJSON = JSON.parse(spec);
				spec = JSON.stringify(specJSON, null, 2);
			} catch (e) {
				toast.error($i18n.t('Please enter a valid JSON spec'));
				loading = false;
				return;
			}
		}

		if (headers) {
			try {
				const _headers = JSON.parse(headers);
				if (typeof _headers !== 'object' || Array.isArray(_headers)) {
					throw new Error('Headers must be a valid JSON object');
				}
				headers = JSON.stringify(_headers, null, 2);
			} catch (error) {
				toast.error($i18n.t('Headers must be a valid JSON object'));
				loading = false;
				return;
			}
		}

		const connection = {
			type,
			url,

			spec_type,
			spec,
			path,

			auth_type,
			headers: headers ? JSON.parse(headers) : undefined,

			key,
			config: {
				enable: enable,
				function_name_filter_list: functionNameFilterList,
				category_id: categoryId || null
			},
			info: {
				id: id,
				name: name,
				description: description,
				...(oauthClientInfo ? { oauth_client_info: oauthClientInfo } : {})
			}
		};

		await onSubmit(connection);

		loading = false;
		show = false;

		// reset form
		type = 'openapi';
		url = '';

		spec_type = 'url';
		spec = '';
		path = 'openapi.json';

		key = '';
		auth_type = 'bearer';

		id = '';
		name = '';
		description = '';

		oauthClientInfo = null;

		enable = true;
		functionNameFilterList = '';
		categoryId = '';
	};

	const init = () => {
		if (connection) {
			type = connection?.type ?? 'openapi';
			url = connection.url;

			spec_type = connection?.spec_type ?? 'url';
			spec = connection?.spec ?? '';
			path = connection?.path ?? 'openapi.json';

			auth_type = connection?.auth_type ?? 'bearer';
			headers = connection?.headers ? JSON.stringify(connection.headers, null, 2) : '';

			key = connection?.key ?? '';

			id = connection.info?.id ?? '';
			name = connection.info?.name ?? '';
			description = connection.info?.description ?? '';
			oauthClientInfo = connection.info?.oauth_client_info ?? null;

			enable = connection.config?.enable ?? true;
			functionNameFilterList = connection.config?.function_name_filter_list ?? '';
			categoryId = connection.config?.category_id ?? '';
		}
	};

	const loadCategories = async () => {
		try {
			const res = await getToolCategories(localStorage.token).catch(() => null);
			if (res?.items) {
				categories = res.items;
			}
		} catch {
			categories = [];
		}
	};

	$: if (show) {
		init();
		loadCategories();
	}

	onMount(() => {
		init();
		loadCategories();
	});
</script>

<Modal size="sm" bind:show>
	<div>
		<div class="flex justify-between items-center px-6 pt-5 pb-4">
			<div class="text-lg font-semibold text-gray-900 dark:text-gray-100">
				{#if edit}
					{$i18n.t('Edit Connection')}
				{:else}
					{$i18n.t('Add Connection')}
				{/if}
			</div>

			<div class="flex items-center gap-3">
				<div class="flex gap-2 text-xs justify-end">
					<button
						class="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:underline transition-colors"
						type="button"
						on:click={() => {
							inputElement?.click();
						}}
					>
						{$i18n.t('Import')}
					</button>

					<button
						class="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:underline transition-colors"
						type="button"
						on:click={exportHandler}
					>
						{$i18n.t('Export')}
					</button>
				</div>

				<button
					class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
					aria-label={$i18n.t('Close')}
					on:click={() => {
						show = false;
					}}
					type="button"
				>
					<XMark className={'size-5'} />
				</button>
			</div>
		</div>

		<div class="px-6 pb-6 dark:text-gray-200">
			<input
				bind:this={inputElement}
				type="file"
				hidden
				accept=".json"
				on:change={(e) => {
					importHandler(e);
				}}
			/>

			<form class="flex flex-col w-full space-y-3" on:submit|preventDefault={submitHandler}>
				<!-- Type selector -->
				<div class="flex flex-col w-full">
					<label
						for="type-input"
						class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
					>
						{$i18n.t('Type')}
					</label>

					<div
						class="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 transition-all"
					>
						<select
							id="type-input"
							class="flex-1 min-w-0 text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden dark:bg-gray-800/50"
							bind:value={type}
						>
							<option value="openapi">{$i18n.t('OpenAPI')}</option>
							<option value="mcp">{$i18n.t('MCP')} - {$i18n.t('Streamable HTTP')}</option>
						</select>

						<Tooltip content={enable ? $i18n.t('Enabled') : $i18n.t('Disabled')}>
							<Switch bind:state={enable} />
						</Tooltip>
					</div>
				</div>

				<!-- Name + ID -->
				<div class="flex gap-3">
					<div class="flex flex-col flex-1 min-w-0">
						<label
							for="enter-name"
							class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
						>
							{$i18n.t('Name')}
						</label>

						<div
							class="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
						>
							<input
								id="enter-name"
								class="flex-1 min-w-0 text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
								type="text"
								bind:value={name}
								placeholder={$i18n.t('Enter name')}
								autocomplete="off"
							/>
						</div>
					</div>

					{#if !direct}
						<div class="flex flex-col flex-1 min-w-0">
							<label
								for="enter-id"
								class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide flex items-center gap-1"
							>
								<span>{$i18n.t('ID')}</span>
								{#if type !== 'mcp'}
									<span class="opacity-60 normal-case tracking-normal text-[10px]"
										>({$i18n.t('optional')})</span
									>
								{/if}
							</label>

							<div
								class="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
							>
								<input
									id="enter-id"
									class="flex-1 min-w-0 text-sm font-mono text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
									type="text"
									bind:value={id}
									placeholder="auto"
									autocomplete="off"
									required={type === 'mcp'}
								/>
							</div>
						</div>
					{/if}
				</div>

				<!-- Description -->
				<div class="flex flex-col w-full">
					<label
						for="description"
						class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
					>
						{$i18n.t('Description')}
					</label>

					<div
						class="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
					>
						<input
							id="description"
							class="flex-1 min-w-0 text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
							type="text"
							bind:value={description}
							placeholder={$i18n.t('Enter description')}
							autocomplete="off"
						/>
					</div>
				</div>

				<!-- Category -->
				<div class="flex flex-col w-full">
					<label
						for="select-category"
						class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide flex items-center gap-1"
					>
						<span>{$i18n.t('Category')}</span>
						<span class="opacity-60 normal-case tracking-normal text-[10px]"
							>({$i18n.t('optional')})</span
						>
					</label>

					<div
						class="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 transition-all"
					>
						<select
							id="select-category"
							class="flex-1 min-w-0 text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden dark:bg-gray-800/50"
							bind:value={categoryId}
						>
							<option value="">{$i18n.t('Uncategorized')}</option>
							{#each categories as cat (cat.id)}
								<option value={cat.id}>{cat.name}</option>
							{/each}
						</select>
					</div>

					<p class="mt-1 text-xs text-gray-400 dark:text-gray-500">
						{$i18n.t(
							'Visibility is inherited from the selected category. Servers without a category are visible to all users.'
						)}
					</p>
				</div>

				<!-- URL -->
				<div class="flex flex-col w-full">
					<label
						for="api-base-url"
						class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
					>
						{$i18n.t('URL')}
					</label>

					<div
						class="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
					>
						<input
							id="api-base-url"
							class="flex-1 min-w-0 text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
							type="text"
							bind:value={url}
							placeholder={$i18n.t('API Base URL')}
							autocomplete="off"
							required
						/>

						<Tooltip content={$i18n.t('Verify Connection')}>
							<button
								class="shrink-0 p-1 rounded-md text-gray-400 hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-200 transition disabled:opacity-50 disabled:cursor-not-allowed"
								on:click={verifyHandler}
								type="button"
								aria-label={$i18n.t('Verify Connection')}
								disabled={verifying || !url}
							>
								{#if verifying}
									<Spinner className="size-4" />
								{:else}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 20 20"
										fill="currentColor"
										aria-hidden="true"
										class="size-4"
									>
										<path
											fill-rule="evenodd"
											d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
											clip-rule="evenodd"
										/>
									</svg>
								{/if}
							</button>
						</Tooltip>
					</div>
				</div>

				<!-- Auth -->
				<div class="flex flex-col w-full">
					<div class="flex items-center justify-between mb-1.5">
						<label
							for="select-bearer-or-session"
							class="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
						>
							{$i18n.t('Auth')}
						</label>

						{#if auth_type === 'oauth_2.1'}
							<div class="flex items-center gap-2">
								<button
									class="text-xs underline text-gray-700 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200 transition"
									type="button"
									on:click={() => {
										registerOAuthClientHandler();
									}}
								>
									{oauthClientInfo ? $i18n.t('Register Again') : $i18n.t('Register Client')}
								</button>

								{#if !oauthClientInfo}
									<div
										class="text-[10px] font-medium px-1.5 py-px rounded-md bg-yellow-500/20 text-yellow-700 dark:text-yellow-200"
									>
										{$i18n.t('Not Registered')}
									</div>
								{:else}
									<div
										class="text-[10px] font-medium px-1.5 py-px rounded-md bg-green-500/20 text-green-700 dark:text-green-200"
									>
										{$i18n.t('Registered')}
									</div>
								{/if}
							</div>
						{/if}
					</div>

					<div
						class="flex items-stretch gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
					>
						<select
							id="select-bearer-or-session"
							class="shrink-0 text-sm text-gray-700 dark:text-gray-200 bg-transparent dark:bg-gray-800/50 outline-hidden pr-2"
							bind:value={auth_type}
						>
							<option value="none">{$i18n.t('None')}</option>
							<option value="bearer">{$i18n.t('Bearer')}</option>
							<option value="session">{$i18n.t('Session')}</option>

							{#if !direct}
								<option value="system_oauth">{$i18n.t('OAuth')}</option>
								{#if type === 'mcp'}
									<option value="oauth_2.1">{$i18n.t('OAuth 2.1')}</option>
								{/if}
							{/if}
						</select>

						<div class="flex flex-1 items-center min-w-0">
							{#if auth_type === 'bearer'}
								<SensitiveInput
									bind:value={key}
									placeholder={$i18n.t('API Key')}
									required={false}
									outerClassName="flex flex-1 bg-transparent items-center"
									inputClassName="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
									showButtonClassName="pl-1.5 text-gray-400 hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-200 transition bg-transparent"
								/>
							{:else if auth_type === 'none'}
								<div class="text-xs text-gray-500 dark:text-gray-400 self-center">
									{$i18n.t('No authentication')}
								</div>
							{:else if auth_type === 'session'}
								<div class="text-xs text-gray-500 dark:text-gray-400 self-center">
									{$i18n.t('Forwards system user session credentials to authenticate')}
								</div>
							{:else if auth_type === 'system_oauth'}
								<div class="text-xs text-gray-500 dark:text-gray-400 self-center">
									{$i18n.t('Forwards system user OAuth access token to authenticate')}
								</div>
							{:else if auth_type === 'oauth_2.1'}
								<div class="text-xs text-gray-500 dark:text-gray-400 self-center">
									{$i18n.t('Uses OAuth 2.1 Dynamic Client Registration')}
								</div>
							{/if}
						</div>
					</div>
				</div>

				<!-- Advanced toggle + Access -->
				<div class="flex items-center justify-between">
					<button
						type="button"
						class="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition"
						on:click={() => (showAdvanced = !showAdvanced)}
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							viewBox="0 0 20 20"
							fill="currentColor"
							class="w-3 h-3 transition-transform {showAdvanced ? 'rotate-90' : ''}"
						>
							<path
								fill-rule="evenodd"
								d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
								clip-rule="evenodd"
							/>
						</svg>
						{$i18n.t('Advanced')}
					</button>
				</div>

				{#if showAdvanced}
					{#if ['', 'openapi'].includes(type)}
						<div class="flex flex-col w-full">
							<label
								for="select-spec-type"
								class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
							>
								{$i18n.t('OpenAPI Spec')}
							</label>

							<div
								class="flex items-start gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
							>
								<select
									id="select-spec-type"
									class="spec-type-select shrink-0 w-auto text-sm text-gray-700 dark:text-gray-200 bg-transparent dark:bg-gray-800/50 outline-hidden appearance-none pr-4 pl-0 cursor-pointer"
									bind:value={spec_type}
								>
									<option value="url">{$i18n.t('URL')}</option>
									<option value="json">{$i18n.t('JSON')}</option>
								</select>

								<div class="flex flex-1 items-center min-w-0">
									{#if spec_type === 'url'}
										<label for="url-or-path" class="sr-only"
											>{$i18n.t('openapi.json URL or Path')}</label
										>
										<input
											class="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
											type="text"
											id="url-or-path"
											bind:value={path}
											placeholder={$i18n.t('openapi.json URL or Path')}
											autocomplete="off"
											required
										/>
									{:else if spec_type === 'json'}
										<label for="spec-json" class="sr-only">{$i18n.t('JSON Spec')}</label>
										<textarea
											id="spec-json"
											class="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600 resize-y"
											bind:value={spec}
											placeholder={$i18n.t('JSON Spec')}
											autocomplete="off"
											required
											rows="5"
										/>
									{/if}
								</div>
							</div>

							{#if ['', 'url'].includes(spec_type)}
								<p class="mt-1 text-xs text-gray-400 dark:text-gray-500">
									{$i18n.t(`WebUI will make requests to "{{url}}"`, {
										url: path.includes('://')
											? path
											: `${url}${path.startsWith('/') ? '' : '/'}${path}`
									})}
								</p>
							{/if}
						</div>
					{/if}

					{#if !direct}
						<div class="flex flex-col w-full">
							<label
								for="headers-input"
								class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
							>
								{$i18n.t('Headers')}
							</label>

							<div
								class="px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
							>
								<Tooltip
									content={$i18n.t(
										'Enter additional headers in JSON format (e.g. {"X-Custom-Header": "value"}'
									)}
								>
									<Textarea
										className="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
										bind:value={headers}
										placeholder={$i18n.t('Enter additional headers in JSON format')}
										required={false}
										minSize={30}
									/>
								</Tooltip>
							</div>
						</div>
					{/if}
				{/if}

				{#if !direct}
					<div class="flex flex-col w-full">
						<label
							for="function-name-filter-list"
							class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
						>
							{$i18n.t('Function Name Filter List')}
						</label>

						<div
							class="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
						>
							<input
								id="function-name-filter-list"
								class="flex-1 min-w-0 text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
								type="text"
								bind:value={functionNameFilterList}
								placeholder={$i18n.t('Enter function name filter list (e.g. func1, !func2)')}
								autocomplete="off"
							/>
						</div>
					</div>
				{/if}

				<!-- Footer actions -->
				<div
					class="flex items-center justify-between gap-2 pt-3 mt-2 border-t border-gray-100 dark:border-gray-800"
				>
					<div>
						{#if edit}
							<button
								class="px-3 py-1.5 text-sm font-medium rounded-lg text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20 transition-colors"
								type="button"
								on:click={() => {
									onDelete();
									show = false;
								}}
							>
								{$i18n.t('Delete')}
							</button>
						{/if}
					</div>

					<div class="flex items-center gap-2">
						<button
							class="px-3 py-1.5 text-sm font-medium rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
							type="button"
							on:click={() => {
								show = false;
							}}
						>
							{$i18n.t('Cancel')}
						</button>

						<button
							class="px-5 py-1.5 text-sm font-medium bg-gray-900 hover:bg-gray-800 text-white dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100 transition-all rounded-lg shadow-sm flex items-center gap-2 {loading
								? ' cursor-not-allowed opacity-70'
								: ''}"
							type="submit"
							disabled={loading}
						>
							{$i18n.t('Save')}

							{#if loading}
								<Spinner className="size-3.5" />
							{/if}
						</button>
					</div>
				</div>
			</form>
		</div>
	</div>
</Modal>


<style>
	.spec-type-select {
		background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 20 20' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 8 10 12 14 8'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 2px center;
		background-size: 10px 10px;
	}

	:global(.dark) .spec-type-select {
		background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 20 20' fill='none' stroke='%239ca3af' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 8 10 12 14 8'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 2px center;
		background-size: 10px 10px;
	}
</style>

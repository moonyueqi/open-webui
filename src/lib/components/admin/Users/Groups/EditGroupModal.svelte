<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import General from './General.svelte';
	import Users from './Users.svelte';
	import { DEFAULT_PERMISSIONS } from '$lib/constants/permissions';
	import UserPlusSolid from '$lib/components/icons/UserPlusSolid.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	export let onSubmit: Function = () => {};
	export let onDelete: Function = () => {};

	export let show = false;
	export let edit = false;

	export let group = null;
	export let groups = [];

	let selectedTab = 'general';
	let loading = false;
	let showDeleteConfirmDialog = false;
	let userCount = 0;
	let nameError = '';

	export let name = '';
	export let description = '';
	export let data = {};

	export let permissions = DEFAULT_PERMISSIONS;

	$: {
		if (name.trim()) {
			const duplicate = groups.find(
				(g) => g.name.toLowerCase() === name.trim().toLowerCase() && (!edit || g.id !== group?.id)
			);
			nameError = duplicate ? $i18n.t('A group with this name already exists') : '';
		} else {
			nameError = '';
		}
	}

	const submitHandler = async () => {
		if (nameError) {
			toast.error(nameError);
			return;
		}

		loading = true;

		const group = {
			name,
			description,
			data,
			permissions
		};

		await onSubmit(group);

		loading = false;
		show = false;
	};

	const init = () => {
		if (group) {
			name = group.name;
			description = group.description;
			permissions = {
				workspace: { ...DEFAULT_PERMISSIONS.workspace, ...(group?.permissions?.workspace ?? {}) },
				sharing: { ...DEFAULT_PERMISSIONS.sharing, ...(group?.permissions?.sharing ?? {}) },
				access_grants: { ...DEFAULT_PERMISSIONS.access_grants, ...(group?.permissions?.access_grants ?? {}) },
				chat: { ...DEFAULT_PERMISSIONS.chat, ...(group?.permissions?.chat ?? {}) },
				features: { ...DEFAULT_PERMISSIONS.features, ...(group?.permissions?.features ?? {}) }
			};
			data = group?.data ?? {};
		} else {
			name = '';
			description = '';
			data = {};
			permissions = {
				workspace: { ...DEFAULT_PERMISSIONS.workspace },
				sharing: { ...DEFAULT_PERMISSIONS.sharing },
				access_grants: { ...DEFAULT_PERMISSIONS.access_grants },
				chat: { ...DEFAULT_PERMISSIONS.chat },
				features: { ...DEFAULT_PERMISSIONS.features }
			};
			nameError = '';
		}
	};

	$: if (show) {
		selectedTab = 'general';
		userCount = group?.member_count ?? 0;
		init();
	}

	onMount(() => {
		init();
	});
</script>

<ConfirmDialog
	bind:show={showDeleteConfirmDialog}
	on:confirm={() => {
		onDelete();
		show = false;
	}}
/>

<Modal size={edit ? 'lg' : 'sm'} bind:show>
	<div>
		<div class="flex justify-between items-center dark:text-gray-100 px-5 pt-4 pb-3">
			<div class="text-lg font-semibold font-primary">
				{#if edit}
					{$i18n.t('Edit User Group')}
				{:else}
					{$i18n.t('Add User Group')}
				{/if}
			</div>
			<button
				class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="flex flex-col md:flex-row w-full px-5 pb-5 md:space-x-4 dark:text-gray-200">
			<div class="flex flex-col w-full">
				<form
					class="flex flex-col w-full"
					on:submit={(e) => {
						e.preventDefault();
						submitHandler();
					}}
				>
					{#if edit}
						<div class="flex flex-col lg:flex-row w-full h-full pb-2 lg:space-x-5">
							<div
								class="tabs flex flex-row overflow-x-auto gap-1 max-w-full lg:flex-col lg:flex-none lg:w-40 dark:text-gray-200 text-sm font-medium text-left scrollbar-none mb-3 lg:mb-0"
							>
								<button
									class="px-3 py-2.5 min-w-fit rounded-xl flex items-center gap-3 transition-all duration-200 select-none {selectedTab === 'general'
										? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm ring-1 ring-gray-100 dark:ring-gray-700/50'
										: 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-white/60 dark:hover:bg-gray-800/40'}"
									on:click={() => {
										selectedTab = 'general';
									}}
									type="button"
								>
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 16 16"
										fill="currentColor"
										class="size-4 flex-shrink-0 {selectedTab === 'general' ? 'text-blue-600 dark:text-blue-400' : ''}"
									>
										<path
											fill-rule="evenodd"
											d="M6.955 1.45A.5.5 0 0 1 7.452 1h1.096a.5.5 0 0 1 .497.45l.17 1.699c.484.12.94.312 1.356.562l1.321-1.081a.5.5 0 0 1 .67.033l.774.775a.5.5 0 0 1 .034.67l-1.08 1.32c.25.417.44.873.561 1.357l1.699.17a.5.5 0 0 1 .45.497v1.096a.5.5 0 0 1-.45.497l-1.699.17c-.12.484-.312.94-.562 1.356l1.082 1.322a.5.5 0 0 1-.034.67l-.774.774a.5.5 0 0 1-.67.033l-1.322-1.08c-.416.25-.872.44-1.356.561l-.17 1.699a.5.5 0 0 1-.497.45H7.452a.5.5 0 0 1-.497-.45l-.17-1.699a4.973 4.973 0 0 1-1.356-.562L4.108 13.37a.5.5 0 0 1-.67-.033l-.774-.775a.5.5 0 0 1-.034-.67l1.08-1.32a4.971 4.971 0 0 1-.561-1.357l-1.699-.17A.5.5 0 0 1 1 8.548V7.452a.5.5 0 0 1 .45-.497l1.699-.17c.12-.484.312-.94.562-1.356L2.629 4.107a.5.5 0 0 1 .034-.67l.774-.774a.5.5 0 0 1 .67-.033L5.43 3.71a4.97 4.97 0 0 1 1.356-.561l.17-1.699ZM6 8c0 .538.212 1.026.558 1.385l.057.057a2 2 0 0 0 2.828-2.828l-.058-.056A2 2 0 0 0 6 8Z"
											clip-rule="evenodd"
										/>
									</svg>
									<span>{$i18n.t('General')}</span>
								</button>

								<button
									class="px-3 py-2.5 min-w-fit rounded-xl flex items-center gap-3 transition-all duration-200 select-none {selectedTab === 'users'
										? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm ring-1 ring-gray-100 dark:ring-gray-700/50'
										: 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-white/60 dark:hover:bg-gray-800/40'}"
									on:click={() => {
										selectedTab = 'users';
									}}
									type="button"
								>
								<span class="flex-shrink-0 {selectedTab === 'users' ? 'text-violet-600 dark:text-violet-400' : ''}">
									<UserPlusSolid />
								</span>
								<span>{$i18n.t('Users')}</span>
								{#if userCount > 0}
									<span class="text-xs text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded-md">{userCount}</span>
								{/if}
								</button>
							</div>

							<div class="flex-1 mt-1 lg:mt-0 lg:h-[30rem] lg:max-h-[30rem] flex flex-col">
							<div class="w-full h-full overflow-y-auto scrollbar-hidden">
								{#if selectedTab === 'general'}
									<General
										bind:name
										bind:description
										bind:data
										bind:permissions
										{nameError}
										{edit}
										onDelete={() => {
											showDeleteConfirmDialog = true;
										}}
									/>
								{:else if selectedTab === 'users'}
									<Users bind:userCount groupId={group?.id} />
								{/if}
							</div>

							<div class="flex justify-end pt-3 text-sm font-medium gap-2">
								<button
									class="px-4 py-2 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-xl flex items-center gap-1.5 {loading || nameError
										? ' cursor-not-allowed opacity-50'
										: ''}"
									type="submit"
									disabled={loading || !!nameError}
								>
									{$i18n.t('Save')}

									{#if loading}
										<Spinner />
									{/if}
								</button>
							</div>
							</div>
						</div>
					{:else}
						<div class="w-full">
							<General
								bind:name
								bind:description
								bind:data
								bind:permissions
								{nameError}
								{edit}
							/>
						</div>

						<div class="flex justify-end pt-4 text-sm font-medium gap-2">
							<button
								class="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition rounded-xl"
								type="button"
								on:click={() => { show = false; }}
							>
								{$i18n.t('Cancel')}
							</button>
							<button
								class="px-4 py-2 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-xl flex items-center gap-1.5 {loading || nameError
									? ' cursor-not-allowed opacity-50'
									: ''}"
								type="submit"
								disabled={loading || !!nameError}
							>
								{$i18n.t('Create')}

								{#if loading}
									<Spinner />
								{/if}
							</button>
						</div>
					{/if}
				</form>
			</div>
		</div>
	</div>
</Modal>

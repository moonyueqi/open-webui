<script lang="ts">
	import { getContext } from 'svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import { DEFAULT_PERMISSIONS } from '$lib/constants/permissions';

	const i18n = getContext('i18n');

	export let name = '';
	export let color = '';
	export let description = '';
	export let data = {};
	export let nameError = '';

	export let edit = false;
	export let onDelete: Function = () => {};

	// Group permissions (only a minimal subset is surfaced here to match the
	// simplified admin panel; the full permissions page is intentionally not shown).
	export let permissions = {};

	$: {
		if (!permissions.features) {
			permissions = {
				...permissions,
				features: { ...DEFAULT_PERMISSIONS.features, ...(permissions.features ?? {}) }
			};
		}
	}

	$: currentShare = data?.config?.share ?? 'members';
</script>

<div class="flex flex-col gap-4">
	<div class="flex flex-col w-full">
		<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">{$i18n.t('Name')} <span class="text-red-500">*</span></label>
		<input
			class="w-full text-sm px-3 py-2 bg-gray-50 dark:bg-gray-850/60 rounded-xl border {nameError ? 'border-red-400 dark:border-red-500' : 'border-gray-200/60 dark:border-gray-700/40'} placeholder:text-gray-400 dark:placeholder:text-gray-600 outline-hidden focus:border-gray-300 dark:focus:border-gray-600 transition"
			type="text"
			bind:value={name}
			placeholder={$i18n.t('Group Name')}
			autocomplete="off"
			required
		/>
		{#if nameError}
			<div class="mt-1 text-xs text-red-500 dark:text-red-400">{nameError}</div>
		{/if}
	</div>

	<div class="flex flex-col w-full">
		<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">{$i18n.t('Description')} <span class="text-gray-400 dark:text-gray-500 font-normal">（{$i18n.t('Optional')}）</span></label>
		<Textarea
			className="w-full text-sm px-3 py-2 bg-gray-50 dark:bg-gray-850/60 rounded-xl border border-gray-200/60 dark:border-gray-700/40 placeholder:text-gray-400 dark:placeholder:text-gray-600 outline-hidden focus:border-gray-300 dark:focus:border-gray-600 transition resize-none"
			rows={3}
			bind:value={description}
			placeholder={$i18n.t('Group Description')}
		/>
	</div>

	<div class="flex flex-col w-full">
		<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">{$i18n.t('Content Sharing Scope')}</label>
		<div class="text-xs text-gray-400 dark:text-gray-500 mb-2">
			{$i18n.t('Control who can share content (models, knowledge, prompts, etc.) to this group')}
		</div>

		<div class="flex items-center gap-2">
			<button
				type="button"
				class="flex-1 px-3 py-2 text-xs font-medium rounded-lg border transition {currentShare === false || currentShare === 'false' ? 'bg-gray-900 text-white dark:bg-white dark:text-black border-transparent' : 'bg-transparent text-gray-500 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800'}"
				on:click={() => { data.config = { ...(data?.config ?? {}), share: false }; }}
			>
				{$i18n.t('Disabled')}
			</button>
			<button
				type="button"
				class="flex-1 px-3 py-2 text-xs font-medium rounded-lg border transition {currentShare === 'members' ? 'bg-gray-900 text-white dark:bg-white dark:text-black border-transparent' : 'bg-transparent text-gray-500 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800'}"
				on:click={() => { data.config = { ...(data?.config ?? {}), share: 'members' }; }}
			>
				{$i18n.t('Members Only')}
			</button>
			<button
				type="button"
				class="flex-1 px-3 py-2 text-xs font-medium rounded-lg border transition {currentShare === true || currentShare === 'true' ? 'bg-gray-900 text-white dark:bg-white dark:text-black border-transparent' : 'bg-transparent text-gray-500 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800'}"
				on:click={() => { data.config = { ...(data?.config ?? {}), share: true }; }}
			>
				{$i18n.t('Everyone')}
			</button>
		</div>
	</div>

	<div class="flex flex-col w-full">
		<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400"
			>{$i18n.t('Feature Permissions')}</label
		>
		<div class="flex w-full items-center justify-between py-1">
			<div class="self-center text-xs font-medium">
				{$i18n.t('Memories')}
			</div>
			<Switch bind:state={permissions.features.memories} />
		</div>
	</div>
</div>

{#if edit}
	<div class="flex justify-end mt-4 pt-3 border-t border-gray-100 dark:border-gray-800/50">
		<button
			class="px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition flex items-center gap-1.5"
			type="button"
			on:click={() => onDelete()}
		>
			<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="size-3.5">
				<path fill-rule="evenodd" d="M5 3.25V4H2.75a.75.75 0 0 0 0 1.5h.3l.815 8.15A1.5 1.5 0 0 0 5.357 15h5.285a1.5 1.5 0 0 0 1.493-1.35l.815-8.15h.3a.75.75 0 0 0 0-1.5H11v-.75A2.25 2.25 0 0 0 8.75 1h-1.5A2.25 2.25 0 0 0 5 3.25Zm2.25-.75a.75.75 0 0 0-.75.75V4h3v-.75a.75.75 0 0 0-.75-.75h-1.5ZM6.05 6a.75.75 0 0 1 .787.713l.275 5.5a.75.75 0 0 1-1.498.075l-.275-5.5A.75.75 0 0 1 6.05 6Zm3.9 0a.75.75 0 0 1 .712.787l-.275 5.5a.75.75 0 0 1-1.498-.075l.275-5.5A.75.75 0 0 1 9.95 6Z" clip-rule="evenodd" />
			</svg>
			{$i18n.t('Delete Group')}
		</button>
	</div>
{/if}

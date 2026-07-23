<script lang="ts">
	import Switch from '$lib/components/common/Switch.svelte';
	import { config, models, settings, user } from '$lib/stores';
	import { createEventDispatcher, onMount, getContext, tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import ManageModal from './Personalization/ManageModal.svelte';
	const dispatch = createEventDispatcher();

	const i18n = getContext('i18n');

	export let saveSettings: Function;

	let showManageModal = false;

	// Addons
	let enableMemory = false;

	onMount(async () => {
		enableMemory = $settings?.memory ?? false;
	});
</script>

<ManageModal bind:show={showManageModal} />

<form
	id="tab-personalization"
	class="flex flex-col h-full justify-between text-sm"
	on:submit|preventDefault={() => {
		dispatch('save');
	}}
>
	<div class="space-y-5 overflow-y-auto scrollbar-hidden">
		<div class="space-y-3">
			<div class="flex items-center justify-between">
				<div class="text-sm font-medium text-gray-700 dark:text-gray-200">
					{$i18n.t('Memory')}
				</div>

				<Switch
					bind:state={enableMemory}
					on:change={async () => {
						saveSettings({ memory: enableMemory });
					}}
				/>
			</div>

			<div class="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
				{$i18n.t(
					"You can personalize your interactions with LLMs by adding memories through the 'Manage' button below, making them more helpful and tailored to you."
				)}
			</div>

			<div>
				<button
					type="button"
					class="px-4 py-1.5 text-sm font-medium bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200 transition-all rounded-lg shadow-sm"
					on:click={() => {
						showManageModal = true;
					}}
				>
					{$i18n.t('Manage')}
				</button>
			</div>
		</div>
	</div>

	<div class="flex justify-end pt-5 mt-4 border-t border-gray-100 dark:border-gray-800">
		<button
			class="px-4 py-1.5 text-sm font-medium bg-gray-900 hover:bg-gray-800 text-white dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100 transition-all rounded-lg shadow-sm"
			type="submit"
		>
			{$i18n.t('Save')}
		</button>
	</div>
</form>

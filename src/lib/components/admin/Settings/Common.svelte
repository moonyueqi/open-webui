<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { getBackendConfig } from '$lib/apis';
	import { getAdminConfig, updateAdminConfig } from '$lib/apis/auths';
	import { config } from '$lib/stores';
	import Switch from '$lib/components/common/Switch.svelte';

	const i18n = getContext('i18n');

	export let saveHandler: Function = () => {};

	let adminConfig = null;

	const updateHandler = async () => {
		const res = await updateAdminConfig(localStorage.token, adminConfig);

		await config.set(await getBackendConfig());

		if (res) {
			saveHandler();
		} else {
			toast.error($i18n.t('Failed to update settings'));
		}
	};

	onMount(async () => {
		adminConfig = await getAdminConfig(localStorage.token);
	});
</script>

<form
	class="flex flex-col h-full justify-between space-y-3 text-sm"
	on:submit|preventDefault={async () => {
		updateHandler();
	}}
>
	<div class="space-y-3 overflow-y-scroll scrollbar-hidden h-full">
		{#if adminConfig !== null}
			<div class="">
				<div class="mb-3">
					<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('General')}</div>

					<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div class=" mb-2.5 flex w-full justify-between pr-2">
						<div class=" self-center text-xs font-medium">{$i18n.t('Enable New Sign Ups')}</div>

						<Switch bind:state={adminConfig.ENABLE_SIGNUP} />
					</div>
				</div>
			</div>
		{/if}
	</div>

	<div class="flex justify-end pt-3 text-sm font-medium">
		<button
			class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-lg"
			type="submit"
		>
			{$i18n.t('Save')}
		</button>
	</div>
</form>

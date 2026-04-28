<script lang="ts">
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');

	import Modal from '$lib/components/common/Modal.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import MemberSelector from '$lib/components/workspace/common/MemberSelector.svelte';

	export let show = false;
	export let shareUsers = true;
	export let onAdd = (payload: { userIds: string[]; groupIds: string[] }) => {};

	let userIds: string[] = [];
	let groupIds: string[] = [];
	let loading = false;

	const submitHandler = () => {
		loading = true;
		onAdd({ userIds, groupIds });
		show = false;

		userIds = [];
		groupIds = [];
		loading = false;
	};
</script>

<Modal size="sm" bind:show>
	<div class="px-5 pt-5 pb-4">
		<div class="flex items-center justify-between mb-4">
			<h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
				{$i18n.t('Add Access')}
			</h2>
			<button
				class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<form
			class="flex flex-col w-full"
			on:submit|preventDefault={() => {
				submitHandler();
			}}
		>
			<MemberSelector
				bind:userIds
				bind:groupIds
				includeGroups={true}
				includeUsers={shareUsers}
			/>

			<div class="flex justify-end mt-4 pt-3 border-t border-gray-100 dark:border-gray-800">
				<button
					class="px-3.5 py-1.5 text-xs font-medium bg-black hover:bg-gray-800 text-white dark:bg-white dark:text-black dark:hover:bg-gray-200 transition rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
					type="submit"
					disabled={userIds.length === 0 && groupIds.length === 0}
				>
					{$i18n.t('Add')}
					{#if userIds.length > 0 || groupIds.length > 0}
						<span class="ml-1 opacity-75">({userIds.length + groupIds.length})</span>
					{/if}
				</button>
			</div>
		</form>
	</div>
</Modal>

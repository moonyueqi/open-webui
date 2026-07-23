<script lang="ts">
	import { toast } from 'svelte-sonner';
	import dayjs from 'dayjs';
	import { getContext, createEventDispatcher } from 'svelte';

	const dispatch = createEventDispatcher();

	import Modal from '$lib/components/common/Modal.svelte';
	import MemoryModal from './MemoryModal.svelte';
	import { deleteMemoriesByUserId, deleteMemoryById, getMemories } from '$lib/apis/memories';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import { error } from '@sveltejs/kit';
	import localizedFormat from 'dayjs/plugin/localizedFormat';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

	const i18n = getContext('i18n');
	dayjs.extend(localizedFormat);

	export let show = false;

	let memories = [];
	let loading = true;

	let showMemoryModal = false;

	let selectedMemory = null;

	let showClearConfirmDialog = false;

	let onClearConfirmed = async () => {
		const res = await deleteMemoriesByUserId(localStorage.token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res && memories.length > 0) {
			toast.success($i18n.t('Memory cleared successfully'));
			memories = [];
		}
		showClearConfirmDialog = false;
	};

	$: if (show && memories.length === 0 && loading) {
		(async () => {
			memories = await getMemories(localStorage.token);
			loading = false;
		})();
	}
</script>

<Modal size="lg" bind:show>
	<div>
		<div class="flex justify-between items-center dark:text-gray-100 px-5 pt-4 pb-3">
			<div class="text-lg font-semibold self-center">{$i18n.t('Memory')}</div>
			<button
				class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition self-center"
				on:click={() => {
					show = false;
				}}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="w-5 h-5"
				>
					<path
						d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
					/>
				</svg>
			</button>
		</div>

		<div class="flex flex-col w-full px-5 pb-5 dark:text-gray-200">
			<div class="flex flex-col w-full h-[28rem] max-h-screen mb-4 mt-1">
				{#if memories.length > 0}
					<div class="text-left text-sm w-full overflow-y-auto scrollbar-hidden">
						<table class="w-full text-sm text-left text-gray-600 dark:text-gray-400 table-auto">
							<thead
								class="text-xs text-gray-400 dark:text-gray-500 sticky top-0 bg-white dark:bg-gray-900"
							>
								<tr class="border-b border-gray-100 dark:border-gray-800/60">
									<th scope="col" class="px-3 py-2 font-medium">{$i18n.t('Name')}</th>
									<th scope="col" class="px-3 py-2 font-medium hidden md:table-cell">
										{$i18n.t('Path (optional)')}
									</th>
									<th scope="col" class="px-3 py-2 font-medium hidden md:table-cell">
										{$i18n.t('Last Modified')}
									</th>
									<th scope="col" class="px-3 py-2 text-right" />
								</tr>
							</thead>
							<tbody>
								{#each memories as memory}
									<tr
										class="border-b border-gray-50 dark:border-gray-850/30 hover:bg-gray-50/60 dark:hover:bg-gray-800/30 transition-colors group"
									>
										<td class="px-3 py-2">
											<div class="flex items-center gap-1.5">
												{#if memory.type === 'user'}
													<span
														class="shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded-md bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300"
														>{$i18n.t('User')}</span
													>
												{/if}
												<div class="line-clamp-1 text-gray-700 dark:text-gray-200">
													{memory.content}
												</div>
											</div>
										</td>
										<td class="px-3 py-2 hidden md:table-cell">
											<div class="line-clamp-1 text-gray-400 dark:text-gray-500 whitespace-nowrap">
												{memory.path ?? '—'}
											</div>
										</td>
										<td class="px-3 py-2 hidden md:table-cell">
											<div class="whitespace-nowrap text-gray-400 dark:text-gray-500 text-xs">
												{dayjs(memory.updated_at * 1000).format('LLL')}
											</div>
										</td>
										<td class="px-3 py-2">
											<div
												class="flex justify-end w-full gap-0.5 opacity-60 group-hover:opacity-100 transition-opacity"
											>
												<Tooltip content={$i18n.t('Edit')}>
													<button
														class="p-1.5 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-black/5 dark:hover:bg-white/10 rounded-lg transition"
														on:click={() => {
															selectedMemory = memory;
															showMemoryModal = true;
														}}
													>
														<svg
															xmlns="http://www.w3.org/2000/svg"
															fill="none"
															viewBox="0 0 24 24"
															stroke-width="1.5"
															stroke="currentColor"
															class="w-4 h-4"
															><path
																stroke-linecap="round"
																stroke-linejoin="round"
																d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Zm0 0L19.5 7.125"
															/></svg
														>
													</button>
												</Tooltip>

												<Tooltip content={$i18n.t('Delete')}>
													<button
														class="p-1.5 text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition"
														on:click={async () => {
															const res = await deleteMemoryById(
																localStorage.token,
																memory.id
															).catch((error) => {
																toast.error(`${error}`);
																return null;
															});

															if (res) {
																toast.success($i18n.t('Memory deleted successfully'));
																memories = await getMemories(localStorage.token);
															}
														}}
													>
														<svg
															xmlns="http://www.w3.org/2000/svg"
															fill="none"
															viewBox="0 0 24 24"
															stroke-width="1.5"
															stroke="currentColor"
															class="w-4 h-4"
														>
															<path
																stroke-linecap="round"
																stroke-linejoin="round"
																d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0"
															/>
														</svg>
													</button>
												</Tooltip>
											</div>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{:else}
					<div class="flex flex-col items-center justify-center h-full text-center px-4">
						<div
							class="flex items-center justify-center w-12 h-12 rounded-full bg-gray-50 dark:bg-gray-800/60 mb-3"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
								stroke-width="1.5"
								stroke="currentColor"
								class="w-6 h-6 text-gray-400 dark:text-gray-500"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18c-2.305 0-4.408.867-6 2.292m0-14.25v14.25"
								/>
							</svg>
						</div>
						<div class="text-sm text-gray-500 dark:text-gray-400">
							{$i18n.t('Memories accessible by LLMs will be shown here.')}
						</div>
					</div>
				{/if}
			</div>
			<div class="flex text-sm font-medium gap-2">
				<button
					class="px-4 py-1.5 text-sm font-medium bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200 transition-all rounded-lg shadow-sm"
					on:click={() => {
						selectedMemory = null;
						showMemoryModal = true;
					}}>{$i18n.t('Add Memory')}</button
				>
				<button
					class="px-4 py-1.5 text-sm font-medium bg-white dark:bg-gray-800/50 border border-red-200/60 dark:border-red-800/40 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all rounded-lg shadow-sm"
					on:click={() => {
						if (memories.length > 0) {
							showClearConfirmDialog = true;
						} else {
							toast.error($i18n.t('No memories to clear'));
						}
					}}>{$i18n.t('Clear memory')}</button
				>
			</div>
		</div>
	</div>
</Modal>

<ConfirmDialog
	title={$i18n.t('Clear Memory')}
	message={$i18n.t('Are you sure you want to clear all memories? This action cannot be undone.')}
	show={showClearConfirmDialog}
	on:confirm={onClearConfirmed}
	on:cancel={() => {
		showClearConfirmDialog = false;
	}}
/>

<MemoryModal
	bind:show={showMemoryModal}
	memory={selectedMemory}
	on:save={async () => {
		memories = await getMemories(localStorage.token);
	}}
/>

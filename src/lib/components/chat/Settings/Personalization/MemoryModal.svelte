<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import { addNewMemory, updateMemoryById } from '$lib/apis/memories';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	const dispatch = createEventDispatcher();
	const i18n = getContext('i18n');

	export let show = false;
	// When `memory` is provided the modal is in edit mode, otherwise add mode.
	export let memory: { id?: string; content?: string; type?: string; path?: string } | null = null;

	let loading = false;
	let content = '';
	let type: 'user' | 'context' = 'context';
	let path = '';

	$: isEdit = !!(memory && memory.id);

	$: if (show) {
		syncFromMemory();
	}

	const syncFromMemory = () => {
		content = memory?.content ?? '';
		type = (memory?.type as 'user' | 'context') ?? 'context';
		path = memory?.path ?? '';
	};

	const submitHandler = async () => {
		loading = true;

		const trimmedPath = path.trim() === '' ? null : path.trim();

		let res;
		if (isEdit) {
			res = await updateMemoryById(
				localStorage.token,
				memory!.id as string,
				content,
				type,
				trimmedPath
			).catch((error) => {
				toast.error(`${error}`);
				return null;
			});
		} else {
			res = await addNewMemory(localStorage.token, content, type, trimmedPath).catch((error) => {
				toast.error(`${error}`);
				return null;
			});
		}

		if (res) {
			toast.success(
				isEdit ? $i18n.t('Memory updated successfully') : $i18n.t('Memory added successfully')
			);
			content = '';
			path = '';
			type = 'context';
			show = false;
			dispatch('save');
		}

		loading = false;
	};
</script>

<Modal bind:show size="sm">
	<div>
		<div class="flex justify-between items-center dark:text-gray-100 px-5 pt-4 pb-3">
			<div class="text-lg font-semibold self-center">
				{isEdit ? $i18n.t('Edit Memory') : $i18n.t('Add Memory')}
			</div>
			<button
				class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition self-center"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="flex flex-col w-full px-5 pb-5 dark:text-gray-200">
			<form
				class="flex flex-col w-full"
				on:submit|preventDefault={() => {
					submitHandler();
				}}
			>
				<div class="flex flex-col w-full">
					<label
						class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
						>{$i18n.t('Content')}</label
					>
					<div
						class="rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
					>
						<textarea
							bind:value={content}
							class="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent px-3 py-2 outline-hidden"
							rows="5"
							style="resize: vertical;"
							placeholder={$i18n.t('Enter a detail about yourself for your LLMs to recall')}
						/>
					</div>
					<div class="mt-1.5 text-[10px] text-gray-400 dark:text-gray-500 leading-snug">
						ⓘ {$i18n.t(
							'Write in a clear, standalone sentence so the assistant can recall it later (e.g. "Responsible for the Meiyu-season forecast summary; reports use the standard template").'
						)}
					</div>
				</div>

				<div class="flex gap-3 mt-4">
					<div class="flex flex-col w-1/3">
						<label
							class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
							>{$i18n.t('Memory Type')}</label
						>
						<div
							class="rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 transition-all"
						>
							<select
								bind:value={type}
								class="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent px-2.5 py-2 outline-hidden"
							>
								<option value="context">{$i18n.t('Context')}</option>
								<option value="user">{$i18n.t('User')}</option>
							</select>
						</div>
					</div>

					<div class="flex flex-col w-2/3">
						<label
							class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
							>{$i18n.t('Path (optional)')}</label
						>
						<div
							class="rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
						>
							<input
								bind:value={path}
								type="text"
								class="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent px-2.5 py-2 outline-hidden"
								placeholder={$i18n.t('e.g. 工作/气象服务/梅汛期')}
							/>
						</div>
					</div>
				</div>

				<div class="mt-2.5 text-[10px] text-gray-400 dark:text-gray-500 leading-snug space-y-0.5">
					<div>
						<span class="font-medium text-gray-500 dark:text-gray-400"
							>{$i18n.t('Memory Type')}：</span
						>{$i18n.t(
							'"User" = your explicit facts/preferences (e.g. responsibilities, reporting habits); "Context" = background info the assistant observes during chats.'
						)}
					</div>
					<div>
						<span class="font-medium text-gray-500 dark:text-gray-400"
							>{$i18n.t('Path (optional)')}：</span
						>{$i18n.t(
							'A folder-style category to organize memories, e.g. "工作/气象服务/梅汛期". Leave empty if not needed.'
						)}
					</div>
				</div>

				<div class="flex justify-end pt-5 mt-4 border-t border-gray-100 dark:border-gray-800">
					<button
						class="px-4 py-1.5 text-sm font-medium bg-gray-900 hover:bg-gray-800 text-white dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100 transition-all rounded-lg shadow-sm flex items-center gap-1.5 {loading
							? ' cursor-not-allowed opacity-60'
							: ''}"
						type="submit"
						disabled={loading}
					>
						{isEdit ? $i18n.t('Update') : $i18n.t('Add')}

						{#if loading}
							<Spinner />
						{/if}
					</button>
				</div>
			</form>
		</div>
	</div>
</Modal>

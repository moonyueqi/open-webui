<script lang="ts">
	import dayjs from '$lib/dayjs';
	import duration from 'dayjs/plugin/duration';
	import relativeTime from 'dayjs/plugin/relativeTime';

	dayjs.extend(duration);
	dayjs.extend(relativeTime);

	import { getContext } from 'svelte';
	const i18n = getContext('i18n');

	import { capitalizeFirstLetter, formatFileSize } from '$lib/utils';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import DocumentPage from '$lib/components/icons/DocumentPage.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	export let knowledge = null;
	export let selectedFileId = null;
	export let files = [];

	export let onClick = (fileId) => {};
	export let onDelete = (fileId) => {};
</script>

<div class="max-h-full flex flex-col w-full gap-0.5 px-1">
	{#each files as file (file?.id ?? file?.itemId ?? file?.tempId)}
		<button
			class="group flex items-center w-full px-3 py-2.5 rounded-xl text-left transition-all duration-200
				{selectedFileId === (file?.id ?? file?.tempId)
					? 'bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200/60 dark:border-emerald-500/20'
					: 'hover:bg-gray-50 dark:hover:bg-gray-850/60 border border-transparent hover:border-gray-200/60 dark:hover:border-gray-700/40'}"
			type="button"
			on:click={async () => {
				onClick(file?.id ?? file?.tempId);
			}}
		>
			<div class="flex items-center gap-3 flex-1 min-w-0">
				<div class="flex items-center justify-center w-8 h-8 rounded-lg shrink-0
					{file?.status === 'uploading'
						? 'bg-amber-50 dark:bg-amber-500/10'
						: 'bg-gray-100 dark:bg-gray-800 group-hover:bg-gray-200/70 dark:group-hover:bg-gray-700/70'}
					transition-colors">
					{#if file?.status !== 'uploading'}
						<DocumentPage className="size-4 text-gray-500 dark:text-gray-400" />
					{:else}
						<Spinner className="size-3.5 text-amber-500" />
					{/if}
				</div>

				<div class="flex-1 min-w-0">
					<div class="text-sm font-medium line-clamp-1 text-gray-800 dark:text-gray-200">
						{file?.name ?? file?.meta?.name}
					</div>
					<div class="flex items-center gap-2 mt-0.5 text-xs text-gray-500 dark:text-gray-400">
						{#if file?.meta?.size}
							<span>{formatFileSize(file?.meta?.size)}</span>
						{/if}
						{#if file?.meta?.size && (file?.updated_at || file?.user)}
							<span class="text-gray-300 dark:text-gray-600">·</span>
						{/if}
						{#if file?.updated_at}
							<Tooltip content={dayjs(file.updated_at * 1000).format('LLLL')}>
								<span>{dayjs(file.updated_at * 1000).fromNow()}</span>
							</Tooltip>
						{/if}
						{#if file?.user}
							<span class="text-gray-300 dark:text-gray-600">·</span>
							<Tooltip
								content={file?.user?.email ?? $i18n.t('Deleted User')}
								className="flex shrink-0"
								placement="top-start"
							>
								<span class="shrink-0">
									{$i18n.t('By {{name}}', {
										name: capitalizeFirstLetter(
											file?.user?.name ?? file?.user?.email ?? $i18n.t('Deleted User')
										)
									})}
								</span>
							</Tooltip>
						{/if}
					</div>
				</div>
			</div>

			{#if knowledge?.write_access}
				<div class="flex items-center opacity-0 group-hover:opacity-100 transition-opacity ml-2">
					<Tooltip content={$i18n.t('Delete')}>
						<!-- svelte-ignore a11y-click-events-have-key-events -->
						<div
							class="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 hover:text-red-500 transition"
							role="button"
							tabindex="-1"
							on:click|stopPropagation={() => {
								onDelete(file?.id ?? file?.tempId);
							}}
						>
							<XMark className="size-3.5" />
						</div>
					</Tooltip>
				</div>
			{/if}
		</button>
	{/each}
</div>

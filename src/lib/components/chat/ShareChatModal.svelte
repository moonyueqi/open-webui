<script lang="ts">
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { getChatById, shareChatById } from '$lib/apis/chats';
	import { copyToClipboard, createMessagesList } from '$lib/utils';

	import Modal from '../common/Modal.svelte';
	import Link from '../icons/Link.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	export let chatId;
	export let show = false;

	let chat = null;
	let shareUrl = '';
	let messages = [];
	let loading = false;
	const i18n = getContext('i18n');

	const stripHtmlTags = (text: string) => {
		if (!text) return '';
		return text
			.replace(/<details[\s\S]*?<\/details>/gi, '')
			.replace(/<[^>]*>/g, '')
			.replace(/&[a-zA-Z0-9#]+;/g, '')
			.trim();
	};

	const getPreviewMessages = (chat) => {
		if (!chat?.chat) return [];
		const chatContent = chat.chat;
		let msgs = [];
		if (chatContent.history) {
			msgs = createMessagesList(chatContent.history, chatContent.history.currentId);
		} else if (chatContent.messages) {
			msgs = chatContent.messages;
		}
		return msgs
			.map((m) => ({ ...m, content: stripHtmlTags(m.content) }))
			.filter((m) => m.content);
	};

	const generateShareLink = async () => {
		loading = true;
		try {
			const sharedChat = await shareChatById(localStorage.token, chatId);
			shareUrl = `${window.location.origin}/s/${sharedChat.id}`;
			chat = await getChatById(localStorage.token, chatId);
		} finally {
			loading = false;
		}
	};

	const copyShareLink = async () => {
		if (!shareUrl) {
			await generateShareLink();
		}

		const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
		if (isSafari) {
			await navigator.clipboard.write([
				new ClipboardItem({
					'text/plain': new Blob([shareUrl], { type: 'text/plain' })
				})
			]);
		} else {
			copyToClipboard(shareUrl);
		}
		toast.success($i18n.t('Copied shared chat URL to clipboard!'));
	};

	$: if (show) {
		(async () => {
			if (chatId) {
				const _chat = await getChatById(localStorage.token, chatId);
				chat = _chat;
				messages = getPreviewMessages(_chat);
				if (_chat.share_id) {
					shareUrl = `${window.location.origin}/s/${_chat.share_id}`;
				} else {
					await generateShareLink();
				}
			} else {
				chat = null;
				messages = [];
				shareUrl = '';
			}
		})();
	}
</script>

<Modal bind:show size="md">
	<div>
		<div class="flex justify-between dark:text-gray-300 px-5 pt-4 pb-0.5">
			<div class="text-sm font-medium self-center">{$i18n.t('Share Chat')}</div>
			<button
				class="self-center"
				aria-label={$i18n.t('Close')}
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-4'} />
			</button>
		</div>

		{#if chat}
			<div class="px-5 pt-3 pb-4 w-full flex flex-col justify-center">
				{#if messages.length > 0}
					<div
						class="mb-3 rounded-lg overflow-hidden bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700"
					>
						<div
							class="max-h-64 overflow-y-auto px-4 py-3 space-y-3"
						>
							{#each messages as message}
								<div
									class="flex {message.role === 'user'
										? 'justify-end'
										: 'justify-start'}"
								>
									<div
										class="max-w-[80%] px-3 py-2 text-xs {message.role === 'user'
											? 'bg-blue-50 dark:bg-blue-900/30 text-gray-700 dark:text-gray-200 rounded-2xl rounded-br-sm'
											: 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-2xl rounded-bl-sm'}"
									>
										<div class="whitespace-pre-wrap break-words line-clamp-4">
											{message.content}
										</div>
									</div>
								</div>
							{/each}
						</div>
					</div>
				{/if}

				<div class="text-xs text-gray-400 dark:text-gray-500 mb-2">
					{$i18n.t(
						'Users with the URL will be able to view the shared chat.'
					)}
				</div>

				<div class="flex items-center gap-2">
					<input
						type="text"
						class="flex-1 text-xs bg-gray-50 dark:bg-gray-800 text-gray-400 dark:text-gray-500 border border-gray-100 dark:border-gray-700 rounded-lg px-3 py-1.5 outline-none"
						value={shareUrl}
						placeholder={loading ? $i18n.t('Generating link...') : ''}
						readonly
					/>
					<button
						class="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-lg shrink-0"
						type="button"
						id="copy-and-share-chat-button"
						disabled={loading}
						on:click={copyShareLink}
					>
						<Link />
						{$i18n.t('Copy Link')}
					</button>
				</div>
			</div>
		{/if}
	</div>
</Modal>

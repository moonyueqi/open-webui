<script lang="ts">
	import { onMount, tick, getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import dayjs from 'dayjs';

	import { settings, chatId, WEBUI_NAME, models, config } from '$lib/stores';
	import { convertMessagesToHistory, createMessagesList } from '$lib/utils';
	import { WEBUI_BASE_URL } from '$lib/constants';

	import { getChatByShareId, cloneSharedChatById, updateChatById } from '$lib/apis/chats';

	import Messages from '$lib/components/chat/Messages.svelte';

	import { getUserInfoById, getUserSettings } from '$lib/apis/users';
	import { getModels } from '$lib/apis';
	import { toast } from 'svelte-sonner';
	import localizedFormat from 'dayjs/plugin/localizedFormat';

	const i18n = getContext('i18n');
	dayjs.extend(localizedFormat);

	let loaded = false;
	let expired = false;

	let autoScroll = true;
	let processing = '';
	let messagesContainerElement: HTMLDivElement;

	// let chatId = $page.params.id;
	let showModelSelector = false;
	let selectedModels = [''];

	let chat = null;
	let user = null;

	let title = '';
	let files = [];

	let messages = [];
	let history = {
		messages: {},
		currentId: null
	};

	$: messages = createMessagesList(history, history.currentId);

	$: if ($page.params.id) {
		(async () => {
			if (await loadSharedChat()) {
				await tick();
				loaded = true;
			} else {
				expired = true;
				setTimeout(() => {
					goto('/');
				}, 3000);
			}
		})();
	}

	//////////////////////////
	// Web functions
	//////////////////////////

	const loadSharedChat = async () => {
		const userSettings = await getUserSettings(localStorage.token).catch((error) => {
			console.error(error);
			return null;
		});

		if (userSettings) {
			settings.set(userSettings.ui);
		} else {
			let localStorageSettings = {} as Parameters<(typeof settings)['set']>[0];

			try {
				localStorageSettings = JSON.parse(localStorage.getItem('settings') ?? '{}');
			} catch (e: unknown) {
				console.error('Failed to parse settings from localStorage', e);
			}

			settings.set(localStorageSettings);
		}

		await models.set(
			await getModels(
				localStorage.token,
				$config?.features?.enable_direct_connections && ($settings?.directConnections ?? null)
			)
		);
		await chatId.set($page.params.id);
		chat = await getChatByShareId(localStorage.token, $chatId).catch(async (error) => {
			return null;
		});

		if (chat) {
			user = await getUserInfoById(localStorage.token, chat.user_id).catch((error) => {
				console.error(error);
				return null;
			});

			const chatContent = chat.chat;

			if (chatContent) {
				console.log(chatContent);

				selectedModels =
					(chatContent?.models ?? undefined) !== undefined
						? chatContent.models
						: [chatContent.models ?? ''];
				history =
					(chatContent?.history ?? undefined) !== undefined
						? chatContent.history
						: convertMessagesToHistory(chatContent.messages);
				title = chatContent.title;

				autoScroll = true;
				await tick();

				if (messages.length > 0 && messages.at(-1)?.id && messages.at(-1)?.id in history.messages) {
					history.messages[messages.at(-1)?.id].done = true;
				}
				await tick();

				return true;
			} else {
				return null;
			}
		}
	};

	const cloneSharedChat = async () => {
		if (!chat) return;

		const res = await cloneSharedChatById(localStorage.token, chat.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			const localizedTitle = $i18n.t('Clone of {{TITLE}}', { TITLE: title });
			await updateChatById(localStorage.token, res.id, { title: localizedTitle });
			goto(`/c/${res.id}`);
		}
	};
</script>

<svelte:head>
	<title>
		{title
			? `${title.length > 30 ? `${title.slice(0, 30)}...` : title} • ${$WEBUI_NAME}`
			: `${$WEBUI_NAME}`}
	</title>
</svelte:head>

{#if expired}
	<div
		class="h-screen max-h-[100dvh] w-full flex flex-col items-center justify-center bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300"
	>
		<div class="text-center space-y-4">
			<svg
				xmlns="http://www.w3.org/2000/svg"
				fill="none"
				viewBox="0 0 24 24"
				stroke-width="1.5"
				stroke="currentColor"
				class="size-12 mx-auto text-gray-400"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M13.181 8.68a4.503 4.503 0 0 1 1.903 6.405m-9.768-2.782L3.56 14.06a4.5 4.5 0 0 0 6.364 6.365l.164-.164m-1.736-1.736 7.07-7.07m-4.242 8.485a4.503 4.503 0 0 1-6.364-6.364l1.757-1.757m9.768 2.782 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-.164.163"
				/>
			</svg>
			<p class="text-lg font-medium">{$i18n.t('This shared link has expired')}</p>
			<p class="text-sm text-gray-400">{$i18n.t('Redirecting to new chat...')}</p>
			<div class="flex justify-center pt-2">
				<div class="animate-spin rounded-full h-5 w-5 border-2 border-gray-300 border-t-gray-600"></div>
			</div>
		</div>
	</div>
{:else if loaded}
	<div
		class="h-screen max-h-[100dvh] w-full flex flex-col text-gray-700 dark:text-gray-100 bg-white dark:bg-gray-900"
	>
		<div class="fixed top-4 left-5 z-10">
			<img
				src="{WEBUI_BASE_URL}/static/auth-form-logo.png"
				class="h-7 w-auto object-contain dark:invert"
				alt="logo"
				draggable="false"
			/>
		</div>

		<div class="flex flex-col flex-auto justify-center relative">
			<div class=" flex flex-col w-full flex-auto overflow-auto h-0" id="messages-container">
				<div
					class="pt-16 px-2 w-full {($settings?.widescreenMode ?? null)
						? 'max-w-full'
						: 'max-w-5xl'} mx-auto"
				>
					<div class="px-3">
						<h1 class="text-xl font-bold text-gray-900 dark:text-gray-100 line-clamp-1 m-0">
							{title}
						</h1>
						<time
							class="text-xs text-gray-400"
							datetime={new Date(chat?.chat?.timestamp || Date.now()).toISOString()}
						>
							{dayjs(chat.chat.timestamp).format('LLL')}
						</time>
					</div>
					<div class="mx-3 mt-3 border-b border-gray-200 dark:border-gray-700"></div>
				</div>

				<div class=" h-full w-full flex flex-col py-2" role="main">
					<div class="w-full shared-chat-messages">
						<Messages
							className="h-full flex pt-4 pb-8 "
							{user}
							chatId={$chatId}
							readOnly={true}
							{selectedModels}
							{processing}
							bind:history
							bind:messages
							bind:autoScroll
							bottomPadding={files.length > 0}
							sendMessage={() => {}}
							continueResponse={() => {}}
							regenerateResponse={() => {}}
						/>
					</div>
				</div>
			</div>

			<div
				class="absolute bottom-0 right-0 left-0 flex justify-center w-full bg-linear-to-b from-transparent to-white dark:to-gray-900"
			>
				<div class="pb-5">
					<button
						class="share-continue-btn px-4 py-2 text-sm font-medium text-white transition rounded-lg flex items-center gap-1.5"
						on:click={cloneSharedChat}
					>
						<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-4">
							<path stroke-linecap="round" stroke-linejoin="round" d="M12 20.25c4.97 0 9-3.694 9-8.25s-4.03-8.25-9-8.25S3 7.444 3 12c0 2.104.859 4.023 2.273 5.48.432.447.74 1.04.586 1.641a4.483 4.483 0 0 1-.923 1.785A5.969 5.969 0 0 0 6 21c1.282 0 2.47-.402 3.445-1.087.81.22 1.668.337 2.555.337Z" />
						</svg>
						{$i18n.t('Continue asking the intelligent forecaster')}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	.share-continue-btn {
		background-color: #0011FF;
	}
	.share-continue-btn:hover {
		background-color: #000de6;
	}
</style>
